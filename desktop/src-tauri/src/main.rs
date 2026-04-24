// tauri v2 desktop shell for loom. responsibilities:
//   1. bootstrap LOOM_SECRET_KEY + LOOM_STORAGE_SIGNING_SECRET via
//      tauri-plugin-store (generated once per install; persisted).
//   2. launch the python backend as a sidecar with lite-profile env.
//   3. block-wait for /api/v1/health to return 200 before showing UI.
//   4. kill the sidecar on every catchable exit path (window close,
//      signal, panic, sidecar-death).
//   5. expose ipc commands for the storage ux flow: pick_directory,
//      disk_usage, persist_data_directory, restart_backend.
#![cfg_attr(
    all(not(debug_assertions), target_os = "windows"),
    windows_subsystem = "windows"
)]

use std::panic;
use std::path::{Path, PathBuf};
use std::sync::Mutex;
use std::time::Duration;

use rand::RngCore;
use rand::rngs::OsRng;
use serde::{Deserialize, Serialize};
use sysinfo::Disks;
use tauri::{AppHandle, Manager, RunEvent, WindowEvent};
use tauri_plugin_dialog::DialogExt;
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

// user preferences live in their own store so they can be edited
// (or deleted for a reset) without touching secrets.
const CONFIG_STORE_PATH: &str = "config.json";
const KEY_DATA_DIR: &str = "data_dir";

#[derive(Debug, Clone, Serialize, Deserialize)]
struct LoomConfig {
    // user-chosen data dir (originals, derivatives, sqlite). none on
    // first run; the frontend triggers a dialog and persists it via
    // the ``persist_data_directory`` command.
    data_dir: Option<PathBuf>,
}

impl LoomConfig {
    fn resolve_data_dir(&self) -> PathBuf {
        if let Some(dir) = &self.data_dir {
            return dir.clone();
        }
        // fallback: ~/.loom/data. used on first launch before the
        // user picks a directory in the first-run flow.
        match dirs::home_dir() {
            Some(home) => home.join(".loom").join("data"),
            None => PathBuf::from(".loom/data"),
        }
    }
}

#[derive(Clone)]
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

    fn replace(&self, child: CommandChild) {
        if let Ok(mut guard) = self.0.lock() {
            if let Some(old) = guard.take() {
                let _ = old.kill();
            }
            *guard = Some(child);
        }
    }
}

// shared state held across commands so ``restart_backend`` can
// respawn the sidecar with the same secrets but a fresh config.
struct BackendState(Mutex<BootstrapSecrets>);

#[derive(Debug, Clone, Serialize)]
struct DiskUsage {
    free: u64,
    total: u64,
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

fn load_config(app: &AppHandle) -> Result<LoomConfig, String> {
    let store = app
        .store(CONFIG_STORE_PATH)
        .map_err(|e| format!("failed to open config store: {e}"))?;
    let data_dir = store.get(KEY_DATA_DIR).and_then(|value| {
        value.as_str().map(|s| PathBuf::from(s.to_string()))
    });
    Ok(LoomConfig { data_dir })
}

fn save_data_dir(app: &AppHandle, path: &Path) -> Result<(), String> {
    let store = app
        .store(CONFIG_STORE_PATH)
        .map_err(|e| format!("failed to open config store: {e}"))?;
    store.set(
        KEY_DATA_DIR,
        serde_json::Value::String(path.display().to_string()),
    );
    store
        .save()
        .map_err(|e| format!("failed to persist config: {e}"))?;
    Ok(())
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

// ipc command: open a native folder picker. returns the chosen path
// (utf-8) or None if the user cancelled.
#[tauri::command]
async fn pick_directory(app: AppHandle) -> Result<Option<String>, String> {
    // the dialog plugin's ``pick_folder`` uses a callback; wrap it in
    // a oneshot so the async command can await the user's choice.
    let (tx, rx) = tokio::sync::oneshot::channel();
    app.dialog().file().pick_folder(move |path| {
        let _ = tx.send(path);
    });
    let path = rx
        .await
        .map_err(|e| format!("folder picker channel closed: {e}"))?;
    match path {
        Some(p) => {
            // FilePath can be a plain path or a uri; prefer the path
            // form since the backend consumes filesystem paths.
            let as_path = p.into_path().map_err(|e| e.to_string())?;
            Ok(Some(as_path.display().to_string()))
        }
        None => Ok(None),
    }
}

// ipc command: return free/total bytes for the disk that contains
// ``path``. used as a quick local advisory before the backend's
// /storage/check roundtrip. returns zeroed counts if no disk matches
// rather than erroring — callers use the backend response for the
// authoritative answer.
#[tauri::command]
fn disk_usage(path: String) -> Result<DiskUsage, String> {
    let target = PathBuf::from(&path);
    let disks = Disks::new_with_refreshed_list();

    // pick the disk whose mount point is the longest prefix of the
    // target path. longer prefixes win so nested mounts beat the
    // root mount.
    let mut best: Option<(&sysinfo::Disk, usize)> = None;
    for disk in disks.list() {
        let mount = disk.mount_point();
        if target.starts_with(mount) {
            let len = mount.as_os_str().len();
            if best.map_or(true, |(_, n)| len > n) {
                best = Some((disk, len));
            }
        }
    }

    let (free, total) = match best {
        Some((disk, _)) => (disk.available_space(), disk.total_space()),
        None => (0, 0),
    };
    Ok(DiskUsage { free, total })
}

// ipc command: persist the user's chosen data directory so the next
// launch (and any subsequent restart_backend) picks it up.
#[tauri::command]
fn persist_data_directory(
    app: AppHandle,
    path: String,
) -> Result<(), String> {
    save_data_dir(&app, Path::new(&path))
}

// ipc command: kill the running sidecar and respawn it under the
// latest persisted data dir. blocks until the new backend answers
// /api/v1/health so the ui can trust the restart succeeded.
#[tauri::command]
async fn restart_backend(app: AppHandle) -> Result<(), String> {
    let sidecar_state = app.state::<SidecarProcess>();
    sidecar_state.take_and_kill();

    let config = load_config(&app)?;
    let secrets = {
        let backend_state = app.state::<BackendState>();
        let guard = backend_state
            .0
            .lock()
            .map_err(|_| "backend state poisoned".to_string())?;
        guard.clone()
    };

    let child = spawn_backend(&app, &config, &secrets)?;
    app.state::<SidecarProcess>().replace(child);
    wait_for_health().await
}

fn main() {
    tauri::Builder::default()
        .plugin(tauri_plugin_shell::init())
        .plugin(tauri_plugin_dialog::init())
        .plugin(tauri_plugin_fs::init())
        .plugin(tauri_plugin_store::Builder::default().build())
        .manage(SidecarProcess(Mutex::new(None)))
        .invoke_handler(tauri::generate_handler![
            pick_directory,
            disk_usage,
            persist_data_directory,
            restart_backend,
        ])
        .setup(|app| {
            let handle = app.handle().clone();

            // install panic + signal handlers before spawning the
            // sidecar so they cover bootstrap failures too.
            install_panic_hook(handle.clone());
            install_signal_handlers(handle.clone());

            let secrets = ensure_bootstrap_secrets(&handle)
                .map_err(|e| -> Box<dyn std::error::Error> { e.into() })?;
            app.manage(BackendState(Mutex::new(secrets.clone())));

            let config = load_config(&handle)
                .map_err(|e| -> Box<dyn std::error::Error> { e.into() })?;

            let child = spawn_backend(&handle, &config, &secrets)
                .map_err(|e| -> Box<dyn std::error::Error> { e.into() })?;
            app.state::<SidecarProcess>().replace(child);

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

