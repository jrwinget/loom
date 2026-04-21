// tauri v2 desktop shell for loom. responsibilities:
//   1. launch the python backend as a sidecar with lite-profile env.
//   2. block-wait for /api/v1/health to return 200 before showing UI.
//   3. kill the sidecar on window close.
#![cfg_attr(
    all(not(debug_assertions), target_os = "windows"),
    windows_subsystem = "windows"
)]

use std::path::PathBuf;
use std::sync::Mutex;
use std::time::Duration;

use serde::{Deserialize, Serialize};
use tauri::{Manager, RunEvent, WindowEvent};
use tauri_plugin_shell::process::{CommandChild, CommandEvent};
use tauri_plugin_shell::ShellExt;

const BACKEND_HEALTH_URL: &str = "http://127.0.0.1:8000/api/v1/health";
const HEALTH_TIMEOUT: Duration = Duration::from_secs(60);
const HEALTH_POLL_INTERVAL: Duration = Duration::from_millis(500);

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

// the spawned sidecar handle, held for graceful shutdown.
struct SidecarProcess(Mutex<Option<CommandChild>>);

fn spawn_backend(
    app: &tauri::AppHandle,
    config: &LoomConfig,
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
        .env("LOOM_DATABASE_URL", db_url);

    let (mut rx, child) = sidecar
        .spawn()
        .map_err(|e| format!("failed to spawn sidecar: {e}"))?;

    // drain sidecar stdout/stderr so the process does not block on a
    // full pipe buffer. we just log everything at debug.
    tauri::async_runtime::spawn(async move {
        while let Some(event) = rx.recv().await {
            match event {
                CommandEvent::Stdout(line) | CommandEvent::Stderr(line) => {
                    let text = String::from_utf8_lossy(&line);
                    eprintln!("[loom-backend] {text}");
                }
                CommandEvent::Terminated(payload) => {
                    eprintln!("[loom-backend] terminated: {payload:?}");
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

fn main() {
    tauri::Builder::default()
        .plugin(tauri_plugin_shell::init())
        .plugin(tauri_plugin_dialog::init())
        .plugin(tauri_plugin_fs::init())
        .plugin(tauri_plugin_store::Builder::default().build())
        .manage(SidecarProcess(Mutex::new(None)))
        .setup(|app| {
            // TODO: load LoomConfig from tauri-plugin-store instead of
            // relying on the fallback path.
            let config = LoomConfig { data_dir: None };
            let child = spawn_backend(&app.handle(), &config)
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
                    if let Some(child) =
                        state.0.lock().expect("sidecar mutex poisoned").take()
                    {
                        let _ = child.kill();
                    }
                }
            }
        })
        .build(tauri::generate_context!())
        .expect("error while building tauri application")
        .run(|_app_handle, event| {
            if let RunEvent::ExitRequested { .. } = event {
                // sidecar is already killed via the CloseRequested
                // handler; nothing to do here.
            }
        });
}
