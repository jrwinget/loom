// tauri v2 desktop shell for loom. responsibilities:
//   1. bootstrap LOOM_SECRET_KEY + LOOM_STORAGE_SIGNING_SECRET via
//      tauri-plugin-store (generated once per install; persisted).
//   2. launch the python backend as a sidecar with lite-profile env.
//   3. block-wait for /api/v1/health to return 200 before showing UI.
//   4. kill the sidecar on every catchable exit path (window close,
//      signal, panic, sidecar-death).
#![cfg_attr(
    all(not(debug_assertions), target_os = "windows"),
    windows_subsystem = "windows"
)]

use std::panic;
use std::path::PathBuf;
use std::sync::Mutex;
use std::time::Duration;

use rand::RngCore;
use rand::rngs::OsRng;
use serde::{Deserialize, Serialize};
use tauri::{AppHandle, Manager, RunEvent, WindowEvent};
use tauri_plugin_shell::ShellExt;
use tauri_plugin_shell::process::{CommandChild, CommandEvent};
use tauri_plugin_store::StoreExt;

const BACKEND_HEALTH_URL: &str = "http://127.0.0.1:8000/api/v1/health";
const HEALTH_TIMEOUT: Duration = Duration::from_secs(60);
const HEALTH_POLL_INTERVAL: Duration = Duration::from_millis(500);

// secrets live in their own store file so they are easy to rotate
// by deletion and do not mingle with user-visible preferences.
const SECRETS_STORE_PATH: &str = "secrets.json";
const KEY_SECRET_KEY: &str = "loom_secret_key";
const KEY_STORAGE_SIGNING_SECRET: &str = "loom_storage_signing_secret";
// 32 random bytes -> 64 hex chars; meets the backend's
// validate_secret_key() length floor with room to spare.
const SECRET_BYTES: usize = 32;

#[derive(Debug, Clone, Serialize, Deserialize)]
struct LoomConfig {
    // user-chosen data dir (originals, derivatives, sqlite). none on
    // first run; the frontend will trigger a dialog and persist it.
    data_dir: Option<PathBuf>,
}

impl LoomConfig {
    fn resolve_data_dir(&self) -> PathBuf {
        if let Some(dir) = &self.data_dir {
            return dir.clone();
        }
        // fallback: ~/.loom/data. TODO: prompt on first run and
        // persist via tauri-plugin-store before reaching this path.
        match dirs::home_dir() {
            Some(home) => home.join(".loom").join("data"),
            None => PathBuf::from(".loom/data"),
        }
    }
}

struct BootstrapSecrets {
    secret_key: String,
    storage_signing_secret: String,
}

// the spawned sidecar handle, held for graceful shutdown. every
// cleanup path goes through ``take_and_kill`` so the handle is
// consumed exactly once.
struct SidecarProcess(Mutex<Option<CommandChild>>);

impl SidecarProcess {
    fn take_and_kill(&self) {
        if let Ok(mut guard) = self.0.lock() {
            if let Some(child) = guard.take() {
                let _ = child.kill();
            }
        }
    }
}

fn generate_hex_secret() -> String {
    let mut buf = [0u8; SECRET_BYTES];
    OsRng.fill_bytes(&mut buf);
    hex::encode(buf)
}

fn ensure_bootstrap_secrets(
    app: &AppHandle,
) -> Result<BootstrapSecrets, String> {
    let store = app
        .store(SECRETS_STORE_PATH)
        .map_err(|e| format!("failed to open secrets store: {e}"))?;

    let read_or_generate = |key: &str| -> String {
        if let Some(value) = store.get(key) {
            if let Some(existing) = value.as_str() {
                if !existing.is_empty() {
                    return existing.to_string();
                }
            }
        }
        let fresh = generate_hex_secret();
        store.set(key, serde_json::Value::String(fresh.clone()));
        fresh
    };

    let secret_key = read_or_generate(KEY_SECRET_KEY);
    let storage_signing_secret =
        read_or_generate(KEY_STORAGE_SIGNING_SECRET);

    store
        .save()
        .map_err(|e| format!("failed to persist secrets: {e}"))?;

    Ok(BootstrapSecrets {
        secret_key,
        storage_signing_secret,
    })
}

fn spawn_backend(
    app: &AppHandle,
    config: &LoomConfig,
    secrets: &BootstrapSecrets,
) -> Result<CommandChild, String> {
    let data_dir = config.resolve_data_dir();
    let db_path = data_dir.join("loom.db");
    let db_url = format!("sqlite+aiosqlite:///{}", db_path.display());

    let sidecar = app
        .shell()
        .sidecar("loom-backend")
        .map_err(|e| format!("failed to locate sidecar: {e}"))?
        .env("LOOM_DEPLOYMENT_PROFILE", "lite")
        .env("LOOM_DATA_DIR", data_dir.display().to_string())
        .env("LOOM_DATABASE_URL", db_url)
        .env("LOOM_SECRET_KEY", secrets.secret_key.clone())
        .env(
            "LOOM_STORAGE_SIGNING_SECRET",
            secrets.storage_signing_secret.clone(),
        );

    let (mut rx, child) = sidecar
        .spawn()
        .map_err(|e| format!("failed to spawn sidecar: {e}"))?;

    // drain sidecar stdout/stderr so the process does not block on a
    // full pipe buffer. log everything at debug. on Terminated, drop
    // our handle (the child is gone anyway) and tell the shell to
    // exit so the UI does not hang on a dead backend — see #57.
    let app_handle = app.clone();
    tauri::async_runtime::spawn(async move {
        while let Some(event) = rx.recv().await {
            match event {
                CommandEvent::Stdout(line) | CommandEvent::Stderr(line) => {
                    let text = String::from_utf8_lossy(&line);
                    eprintln!("[loom-backend] {text}");
                }
                CommandEvent::Terminated(payload) => {
                    eprintln!("[loom-backend] terminated: {payload:?}");
                    if let Some(state) =
                        app_handle.try_state::<SidecarProcess>()
                    {
                        if let Ok(mut guard) = state.0.lock() {
                            let _ = guard.take();
                        }
                    }
                    app_handle.exit(1);
                    break;
                }
                _ => {}
            }
        }
    });

    Ok(child)
}

async fn wait_for_health() -> Result<(), String> {
    let client = reqwest::Client::builder()
        .timeout(Duration::from_secs(2))
        .build()
        .map_err(|e| format!("reqwest build failed: {e}"))?;

    let deadline = std::time::Instant::now() + HEALTH_TIMEOUT;
    loop {
        if let Ok(resp) = client.get(BACKEND_HEALTH_URL).send().await {
            if resp.status().is_success() {
                return Ok(());
            }
        }
        if std::time::Instant::now() >= deadline {
            return Err(format!(
                "backend did not respond to {BACKEND_HEALTH_URL} within {:?}",
                HEALTH_TIMEOUT
            ));
        }
        tokio::time::sleep(HEALTH_POLL_INTERVAL).await;
    }
}

fn install_signal_handlers(app_handle: AppHandle) {
    // ctrlc with the ``termination`` feature catches SIGINT, SIGTERM
    // and SIGHUP on unix (plus Ctrl+C/Break on windows). SIGKILL
    // cannot be caught by design — closing that hole requires the
    // child to watch its parent and is tracked separately.
    let _ = ctrlc::set_handler(move || {
        eprintln!("[loom] termination signal received; cleaning up");
        if let Some(state) = app_handle.try_state::<SidecarProcess>() {
            state.take_and_kill();
        }
        app_handle.exit(0);
    });
}

fn install_panic_hook(app_handle: AppHandle) {
    let default = panic::take_hook();
    panic::set_hook(Box::new(move |info| {
        eprintln!("[loom] tauri shell panicked; killing sidecar");
        if let Some(state) = app_handle.try_state::<SidecarProcess>() {
            state.take_and_kill();
        }
        default(info);
    }));
}

fn main() {
    tauri::Builder::default()
        .plugin(tauri_plugin_shell::init())
        .plugin(tauri_plugin_dialog::init())
        .plugin(tauri_plugin_fs::init())
        .plugin(tauri_plugin_store::Builder::default().build())
        .manage(SidecarProcess(Mutex::new(None)))
        .setup(|app| {
            let handle = app.handle().clone();

            // install panic + signal handlers before spawning the
            // sidecar so they cover bootstrap failures too.
            install_panic_hook(handle.clone());
            install_signal_handlers(handle.clone());

            let secrets = ensure_bootstrap_secrets(&handle)
                .map_err(|e| -> Box<dyn std::error::Error> { e.into() })?;

            // TODO: load LoomConfig from tauri-plugin-store instead of
            // relying on the fallback path.
            let config = LoomConfig { data_dir: None };
            let child = spawn_backend(&handle, &config, &secrets)
                .map_err(|e| -> Box<dyn std::error::Error> { e.into() })?;
            app.state::<SidecarProcess>()
                .0
                .lock()
                .expect("sidecar mutex poisoned")
                .replace(child);

            // block the setup hook until the backend is healthy so
            // the webview never sees a connection refused.
            tauri::async_runtime::block_on(async {
                wait_for_health().await
            })
            .map_err(|e| -> Box<dyn std::error::Error> { e.into() })?;
            Ok(())
        })
        .on_window_event(|window, event| {
            if let WindowEvent::CloseRequested { .. } = event {
                if let Some(state) = window.try_state::<SidecarProcess>() {
                    state.take_and_kill();
                }
            }
        })
        .build(tauri::generate_context!())
        .expect("error while building tauri application")
        .run(|app_handle, event| {
            // final safety net: cover exit paths that bypass the
            // window CloseRequested handler (RunEvent::Exit fires on
            // normal shutdown; ExitRequested fires when app.exit()
            // is called from a signal handler or the sidecar-
            // terminated branch).
            if matches!(
                event,
                RunEvent::Exit | RunEvent::ExitRequested { .. }
            ) {
                if let Some(state) =
                    app_handle.try_state::<SidecarProcess>()
                {
                    state.take_and_kill();
                }
            }
        });
}
