// tauri v2 desktop shell for loom. responsibilities:
//   1. bootstrap LOOM_SECRET_KEY + LOOM_STORAGE_SIGNING_SECRET via
//      tauri-plugin-store (generated once per install; persisted).
//   2. launch the python backend as a sidecar with lite-profile env.
//   3. poll /api/v1/health off the main thread, emitting
//      ``backend-ready`` or ``backend-error`` so the frontend boot
//      gate can render without ever blocking the os event loop.
//   4. kill the sidecar on every catchable exit path (window close,
//      signal, panic, sidecar-death).
//   5. expose ipc commands for the storage ux flow: pick_directory,
//      disk_usage, persist_data_directory, restart_backend.
//   6. persist rotating shell logs (tauri-plugin-log) that also
//      capture sidecar output, and export a diagnostics zip on
//      request (export_diagnostics).
#![cfg_attr(
    all(not(debug_assertions), target_os = "windows"),
    windows_subsystem = "windows"
)]

mod redact;

use std::panic;
use std::path::{Path, PathBuf};
use std::sync::Arc;
use std::sync::Mutex;
use std::sync::atomic::{AtomicBool, Ordering};
use std::time::Duration;

use rand::TryRng;
use rand::rngs::SysRng;
use serde::{Deserialize, Serialize};
use sysinfo::Disks;
use tauri::{AppHandle, Emitter, Manager, RunEvent, WindowEvent};
use tauri_plugin_dialog::DialogExt;
use tauri_plugin_log::{RotationStrategy, Target, TargetKind};
use tauri_plugin_shell::ShellExt;
use tauri_plugin_shell::process::{CommandChild, CommandEvent};
use tauri_plugin_store::StoreExt;

const BACKEND_HEALTH_URL: &str = "http://127.0.0.1:8000/api/v1/health";
const BACKEND_SHUTDOWN_URL: &str =
    "http://127.0.0.1:8000/api/v1/admin/shutdown";
const HEALTH_TIMEOUT: Duration = Duration::from_secs(60);
const HEALTH_POLL_INTERVAL: Duration = Duration::from_millis(500);
// short, bounded window for the sidecar to flush its 204 and call
// os._exit. anything longer makes the window-close interaction feel
// hung; anything shorter risks racing the loopback roundtrip.
const SHUTDOWN_REQUEST_TIMEOUT: Duration = Duration::from_millis(1500);

// surfaced stderr is rendered inside a <pre> block in the boot
// gate. cap it so a misbehaving backend dumping a multi-mb
// traceback does not push a huge string through the ipc channel
// and into the dom. 4 kib is enough room for any reasonable
// stack trace; anything past it is truncated with an ellipsis.
const MAX_ERROR_PAYLOAD_CHARS: usize = 4096;

fn truncate_error(msg: String) -> String {
    if msg.chars().count() <= MAX_ERROR_PAYLOAD_CHARS {
        return msg;
    }
    let mut out: String = msg.chars().take(MAX_ERROR_PAYLOAD_CHARS).collect();
    out.push_str("… [truncated]");
    out
}

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
    // per-launch shared secret for POST /admin/shutdown. regenerated
    // every time the tauri shell starts so a leaked token from one
    // session cannot terminate a later one. handed to the sidecar via
    // LOOM_SHUTDOWN_TOKEN env and presented back in the X-Loom-
    // Shutdown-Token header on app close.
    shutdown_token: String,
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

// last stderr line captured from the sidecar. populated by the drain
// task and read by the boot watcher to build a meaningful
// ``backend-error`` payload.
#[derive(Default)]
struct LastBackendStderr(Arc<Mutex<Option<String>>>);

// flips to true once the boot watcher emits ``backend-ready`` for
// the current sidecar. used so that a sidecar that dies before
// becoming healthy emits ``backend-error`` rather than ``backend-
// ready``: the watcher only emits ready if it wins the cas race
// against the drain task's terminated branch. reset on every
// respawn from ``restart_backend``.
#[derive(Default)]
struct BootReady(Arc<AtomicBool>);

#[derive(Debug, Clone, Serialize)]
struct DiskUsage {
    free: u64,
    total: u64,
}

fn generate_hex_secret() -> String {
    let mut buf = [0u8; SECRET_BYTES];
    SysRng
        .try_fill_bytes(&mut buf)
        .expect("system rng must provide entropy");
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

    // shutdown token is intentionally NOT persisted: regenerating it
    // per launch is the whole point. it lives only in process memory
    // and the sidecar's env block.
    let shutdown_token = generate_hex_secret();

    Ok(BootstrapSecrets {
        secret_key,
        storage_signing_secret,
        shutdown_token,
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

fn clear_data_dir_preference(app: &AppHandle) -> Result<(), String> {
    let store = app
        .store(CONFIG_STORE_PATH)
        .map_err(|e| format!("failed to open config store: {e}"))?;
    store.delete(KEY_DATA_DIR);
    store
        .save()
        .map_err(|e| format!("failed to persist config: {e}"))?;
    Ok(())
}

// known artefacts produced by the backend under ``data_dir``. anything
// the user dropped into the same folder by hand is intentionally left
// alone — a factory reset wipes Loom's state, not the whole directory.
const PURGE_FILES: &[&str] = &["loom.db", "loom.db-shm", "loom.db-wal"];
const PURGE_DIRS: &[&str] = &["buckets"];

fn purge_lite_data(data_dir: &Path) -> Result<(), String> {
    if !data_dir.exists() {
        // a never-completed first-run can hit this path; treat as a
        // no-op so the caller can still proceed to clear preferences
        // and respawn the sidecar into a fresh first-run state.
        return Ok(());
    }

    for name in PURGE_FILES {
        let path = data_dir.join(name);
        if path.exists() {
            std::fs::remove_file(&path).map_err(|e| {
                format!("failed to delete {}: {e}", path.display())
            })?;
        }
    }

    for name in PURGE_DIRS {
        let path = data_dir.join(name);
        if path.exists() {
            std::fs::remove_dir_all(&path).map_err(|e| {
                format!("failed to delete {}: {e}", path.display())
            })?;
        }
    }

    Ok(())
}

// resolve the bundled host-binaries resource dir (ffmpeg, tesseract
// on linux/windows). returns None when absent — macos bundles none
// by design, and a dev tree only has it after running
// scripts/fetch-desktop-binaries.py — in which case the sidecar env
// is left alone and the engine probes fall back to their remedies.
fn bundled_binaries_dir(app: &AppHandle) -> Option<PathBuf> {
    let dir = app.path().resource_dir().ok()?.join("binaries");
    // the placeholder README ships alone on platforms with no
    // entries; require an actual binary before touching PATH
    let has_binary = ["ffmpeg", "ffmpeg.exe"]
        .iter()
        .any(|name| dir.join(name).is_file());
    if has_binary { Some(dir) } else { None }
}

fn spawn_backend(
    app: &AppHandle,
    config: &LoomConfig,
    secrets: &BootstrapSecrets,
) -> Result<CommandChild, String> {
    let data_dir = config.resolve_data_dir();
    let db_path = data_dir.join("loom.db");
    let db_url = format!("sqlite+aiosqlite:///{}", db_path.display());

    let mut sidecar = app
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
        )
        // no upload cap on desktop: evidence footage is multi-gb and
        // the disk is the real limit. uploads stream to disk, so this
        // does not admit memory exhaustion.
        .env("LOOM_MAX_UPLOAD_SIZE_BYTES", "0")
        .env("LOOM_SHUTDOWN_TOKEN", secrets.shutdown_token.clone());

    // prepend the bundled binaries to PATH so the python side's
    // shutil.which() finds them with zero backend changes; tessdata
    // rides along for the bundled tesseract.
    if let Some(bin_dir) = bundled_binaries_dir(app) {
        let sep = if cfg!(windows) { ";" } else { ":" };
        let current = std::env::var("PATH").unwrap_or_default();
        sidecar = sidecar.env(
            "PATH",
            format!("{}{}{}", bin_dir.display(), sep, current),
        );
        let tessdata = bin_dir.join("tessdata");
        if tessdata.is_dir() {
            sidecar = sidecar
                .env("TESSDATA_PREFIX", tessdata.display().to_string());
        }
    }

    let (mut rx, child) = sidecar
        .spawn()
        .map_err(|e| format!("failed to spawn sidecar: {e}"))?;

    // assign the bootloader to the per-app job object so closing the
    // tauri process cascades termination to any descendant the
    // bootloader spawned. no-op on non-windows targets — those rely
    // on the python-side parent-pid watchdog instead.
    #[cfg(windows)]
    if let Some(job) = app.try_state::<sidecar_job::JobHandle>() {
        let pid = child.pid();
        if let Err(err) = sidecar_job::assign(job.inner(), pid) {
            eprintln!(
                "[loom] failed to assign sidecar pid {pid} to job: {err}"
            );
        }
    }

    // drain sidecar stdout/stderr so the process does not block on a
    // full pipe buffer. every stderr line is also kept in the shared
    // ``LastBackendStderr`` slot so the boot watcher and the
    // terminated branch can build a meaningful error payload.
    let app_handle = app.clone();
    tauri::async_runtime::spawn(async move {
        let last_stderr = app_handle
            .try_state::<LastBackendStderr>()
            .map(|s| s.0.clone());
        let boot_ready = app_handle
            .try_state::<BootReady>()
            .map(|s| s.0.clone());

        while let Some(event) = rx.recv().await {
            match event {
                // route backend output through `log` so it lands in
                // the shell's rotating log files, not just the tty.
                // redact before anything hits the rotating log files
                // (and thus the diagnostics zip): raw sidecar output
                // bypasses the backend's own structlog redaction.
                CommandEvent::Stdout(line) => {
                    let text = redact::redact(&String::from_utf8_lossy(&line));
                    log::info!(target: "sidecar", "{text}");
                }
                CommandEvent::Stderr(line) => {
                    let text = redact::redact(&String::from_utf8_lossy(&line));
                    log::info!(target: "sidecar", "{text}");
                    if let Some(slot) = last_stderr.as_ref() {
                        if let Ok(mut guard) = slot.lock() {
                            *guard = Some(text);
                        }
                    }
                }
                CommandEvent::Terminated(payload) => {
                    let text = redact::redact(&format!("{payload:?}"));
                    log::warn!(target: "sidecar", "terminated: {text}");
                    if let Some(state) =
                        app_handle.try_state::<SidecarProcess>()
                    {
                        if let Ok(mut guard) = state.0.lock() {
                            let _ = guard.take();
                        }
                    }
                    // claim the boot slot so a concurrent watcher
                    // does not also emit ``backend-ready`` for this
                    // same boot attempt. if the cas fails the
                    // watcher already won and this terminated is a
                    // post-boot crash; either way the user needs an
                    // error surface, so emit unconditionally.
                    if let Some(flag) = boot_ready.as_ref() {
                        let _ = flag.compare_exchange(
                            false,
                            true,
                            Ordering::SeqCst,
                            Ordering::SeqCst,
                        );
                    }
                    let message = last_stderr
                        .as_ref()
                        .and_then(|slot| slot.lock().ok()?.clone())
                        .unwrap_or_else(|| {
                            format!(
                                "backend exited unexpectedly: {payload:?}"
                            )
                        });
                    let _ = app_handle
                        .emit("backend-error", truncate_error(message));
                    break;
                }
                _ => {}
            }
        }
    });

    Ok(child)
}

// polls the backend health endpoint until success or the deadline.
// when ``boot_ready`` is supplied the loop also bails if the drain
// task has already flipped the flag (sidecar terminated during
// boot), so the user is not held on the boot panel for the full
// health timeout when the backend is already dead.
async fn wait_for_health(
    boot_ready: Option<Arc<AtomicBool>>,
) -> Result<(), String> {
    let client = reqwest::Client::builder()
        .timeout(Duration::from_secs(2))
        .build()
        .map_err(|e| format!("reqwest build failed: {e}"))?;

    let deadline = std::time::Instant::now() + HEALTH_TIMEOUT;
    loop {
        if let Some(flag) = boot_ready.as_ref() {
            if flag.load(Ordering::SeqCst) {
                return Err("backend exited before answering health".into());
            }
        }
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

// runs the full boot sequence (config + spawn + health wait) off
// the setup hook so the main thread is never blocked. emits
// ``backend-ready`` on success and ``backend-error`` with a string
// payload on every reachable failure path; only one of the two
// fires per boot attempt, gated by the ``BootReady`` cas race
// against the sidecar drain task.
async fn run_initial_boot(app: AppHandle) {
    let secrets = match app.try_state::<BackendState>() {
        Some(state) => match state.0.lock() {
            Ok(guard) => guard.clone(),
            Err(_) => {
                let _ = app.emit(
                    "backend-error",
                    truncate_error(
                        "backend state poisoned during boot".into(),
                    ),
                );
                return;
            }
        },
        None => {
            let _ = app.emit(
                "backend-error",
                truncate_error("bootstrap secrets unavailable".into()),
            );
            return;
        }
    };

    let config = match load_config(&app) {
        Ok(cfg) => cfg,
        Err(err) => {
            let _ = app.emit("backend-error", truncate_error(err));
            return;
        }
    };

    let child = match spawn_backend(&app, &config, &secrets) {
        Ok(c) => c,
        Err(err) => {
            let _ = app.emit("backend-error", truncate_error(err));
            return;
        }
    };
    app.state::<SidecarProcess>().replace(child);

    let boot_ready = app.state::<BootReady>().0.clone();
    match wait_for_health(Some(boot_ready.clone())).await {
        Ok(()) => {
            // only emit ready if the drain task has not already
            // claimed the boot slot via Terminated.
            if boot_ready
                .compare_exchange(
                    false,
                    true,
                    Ordering::SeqCst,
                    Ordering::SeqCst,
                )
                .is_ok()
            {
                let _ = app.emit("backend-ready", ());
            }
        }
        Err(err) => {
            // the drain task may already have emitted via the
            // Terminated branch; the cas tells us which path fires
            // the error payload.
            if boot_ready
                .compare_exchange(
                    false,
                    true,
                    Ordering::SeqCst,
                    Ordering::SeqCst,
                )
                .is_ok()
            {
                let message = app
                    .state::<LastBackendStderr>()
                    .0
                    .lock()
                    .ok()
                    .and_then(|g| g.clone())
                    .unwrap_or(err);
                let _ = app.emit("backend-error", truncate_error(message));
            }
        }
    }
}

// best-effort graceful shutdown: ask the sidecar to release port 8000
// via POST /admin/shutdown (authenticated by the per-launch shared
// secret), wait at most SHUTDOWN_REQUEST_TIMEOUT for the request to
// settle, then fall through to a hard kill regardless of outcome.
//
// the request result is intentionally discarded. the python side
// schedules os._exit ~100ms after responding 204, so by the time the
// reqwest future resolves the process has already begun exiting and a
// subsequent take_and_kill() is a no-op. if the sidecar is wedged or
// the token is wrong (it shouldn't be — we generated and injected it
// in the same launch), the timeout fires and we kill the bootloader.
//
// two entry points share one body:
//   * graceful_shutdown_sidecar_async — awaited from #[tauri::command]
//     async fns (factory_reset, restart_backend). calling block_on
//     from inside an async task nested on tokio's multi-thread runtime
//     panics with "Cannot start a runtime from within a runtime", so
//     the async commands must await directly.
//   * graceful_shutdown_sidecar — sync wrapper for synchronous
//     handlers (ctrlc, panic hook, window CloseRequested, RunEvent).
//     block_on is legal here because the caller is not already on a
//     tokio worker.
async fn graceful_shutdown_sidecar_async(app: &AppHandle) {
    let token = app
        .try_state::<BackendState>()
        .and_then(|state| {
            state.0.lock().ok().map(|guard| guard.shutdown_token.clone())
        })
        .unwrap_or_default();

    if !token.is_empty() {
        let _: Result<_, String> = async {
            let client = reqwest::Client::builder()
                .timeout(SHUTDOWN_REQUEST_TIMEOUT)
                .build()
                .map_err(|e| format!("reqwest build: {e}"))?;
            client
                .post(BACKEND_SHUTDOWN_URL)
                .header("X-Loom-Shutdown-Token", token)
                .send()
                .await
                .map_err(|e| format!("shutdown request: {e}"))
        }
        .await;
    }

    if let Some(state) = app.try_state::<SidecarProcess>() {
        state.take_and_kill();
    }
}

fn graceful_shutdown_sidecar(app: &AppHandle) {
    tauri::async_runtime::block_on(graceful_shutdown_sidecar_async(app));
}

fn install_signal_handlers(app_handle: AppHandle) {
    // ctrlc with the ``termination`` feature catches SIGINT, SIGTERM
    // and SIGHUP on unix (plus Ctrl+C/Break on windows). SIGKILL
    // cannot be caught by design — closing that hole requires the
    // child to watch its parent, which the python sidecar's orphan
    // watchdog handles on unix. windows installs additionally rely on
    // the job object attached at spawn.
    let _ = ctrlc::set_handler(move || {
        eprintln!("[loom] termination signal received; cleaning up");
        graceful_shutdown_sidecar(&app_handle);
        app_handle.exit(0);
    });
}

fn install_panic_hook(app_handle: AppHandle) {
    let default = panic::take_hook();
    panic::set_hook(Box::new(move |info| {
        eprintln!("[loom] tauri shell panicked; killing sidecar");
        // best-effort crash file in the log dir so a later
        // diagnostics export can carry the panic even when the
        // terminal output is long gone. io errors are ignored:
        // we're already crashing.
        write_crash_file(&app_handle, info);
        // skip the graceful path here: we're already crashing and
        // blocking the panic handler for an http roundtrip courts
        // double-faults. fall straight to the hard kill; the python
        // orphan watchdog will pick up any descendants on unix and
        // the job object will on windows.
        if let Some(state) = app_handle.try_state::<SidecarProcess>() {
            state.take_and_kill();
        }
        default(info);
    }));
}

fn unix_now() -> u64 {
    std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .map(|d| d.as_secs())
        .unwrap_or(0)
}

fn write_crash_file(app: &AppHandle, info: &panic::PanicHookInfo<'_>) {
    let Ok(dir) = app.path().app_log_dir() else {
        return;
    };
    if std::fs::create_dir_all(&dir).is_err() {
        return;
    }
    let path = dir.join(format!("crash-{}.txt", unix_now()));
    // PanicHookInfo's Display carries both the payload and the
    // panic location.
    let _ = std::fs::write(&path, format!("{info}\n"));
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
// /api/v1/health so the ui can trust the restart succeeded. on
// success emits ``backend-ready`` so the boot gate flips out of its
// ``booting`` state; on failure emits ``backend-error`` with the
// captured stderr.
#[tauri::command]
async fn restart_backend(app: AppHandle) -> Result<(), String> {
    // graceful first: the abrupt kill path can leave a pyinstaller
    // python child orphaned holding port 8000, which would then prevent
    // the new sidecar from binding. graceful_shutdown asks the sidecar
    // to exit cleanly via /admin/shutdown before falling through to a
    // hard kill on timeout. await the async entry point directly —
    // block_on inside this command would panic on tokio multi-thread.
    graceful_shutdown_sidecar_async(&app).await;

    let config = load_config(&app)?;
    let secrets = {
        let backend_state = app.state::<BackendState>();
        let guard = backend_state
            .0
            .lock()
            .map_err(|_| "backend state poisoned".to_string())?;
        guard.clone()
    };

    // reset boot-resolution state for the new sidecar lifecycle.
    let boot_ready = app.state::<BootReady>().0.clone();
    boot_ready.store(false, Ordering::SeqCst);
    if let Ok(mut guard) = app.state::<LastBackendStderr>().0.lock() {
        *guard = None;
    }

    let child = spawn_backend(&app, &config, &secrets)?;
    app.state::<SidecarProcess>().replace(child);

    match wait_for_health(Some(boot_ready.clone())).await {
        Ok(()) => {
            let won = boot_ready
                .compare_exchange(
                    false,
                    true,
                    Ordering::SeqCst,
                    Ordering::SeqCst,
                )
                .is_ok();
            if won {
                let _ = app.emit("backend-ready", ());
            }
            Ok(())
        }
        Err(err) => {
            // if the drain task has not already emitted, surface the
            // error with the freshest stderr we captured.
            let already = boot_ready
                .compare_exchange(
                    false,
                    true,
                    Ordering::SeqCst,
                    Ordering::SeqCst,
                )
                .is_err();
            if !already {
                let message = app
                    .state::<LastBackendStderr>()
                    .0
                    .lock()
                    .ok()
                    .and_then(|g| g.clone())
                    .unwrap_or_else(|| err.clone());
                let _ = app.emit("backend-error", truncate_error(message));
            }
            Err(err)
        }
    }
}

// ipc command: destructive reset of the local Loom install. used by
// the login-page "Reset Loom" affordance for the operator who can't
// sign in and has no valid recovery code. wipes the sqlite db plus
// the buckets/ subtree under data_dir, clears the data-dir preference
// so the next launch routes through first-run, and respawns the
// sidecar. ``secrets.json`` is intentionally left in place so the
// install's bootstrap secrets stay stable across resets — rotating
// them would invalidate nothing useful once the db is gone.
#[tauri::command]
async fn factory_reset(app: AppHandle) -> Result<(), String> {
    // same port-8000 reasoning as restart_backend: the respawn at the
    // tail of this function needs a clean socket. await the async
    // entry point directly — block_on inside this command would panic
    // on tokio multi-thread.
    graceful_shutdown_sidecar_async(&app).await;

    let config = load_config(&app)?;
    let data_dir = config.resolve_data_dir();

    purge_lite_data(&data_dir)?;
    clear_data_dir_preference(&app)?;

    // restart_backend re-reads the (now-cleared) config, respawns the
    // sidecar against the default ``~/.loom/data`` location, and
    // waits for /api/v1/health. once back up, /first-run/status will
    // report ``first_run_required: true`` and the frontend's existing
    // redirect sends the operator into onboarding.
    restart_backend(app).await
}

// held between the consent check and the install click so the
// operator installs exactly the update they were shown.
struct PendingUpdate(Mutex<Option<tauri_plugin_updater::Update>>);

#[derive(serde::Serialize)]
struct UpdateInfo {
    version: String,
    notes: Option<String>,
}

// ipc command: passive update check. returns the available update's
// metadata or None. never downloads or installs anything — consent
// lives in the ui banner.
#[tauri::command]
async fn check_for_update(
    app: AppHandle,
) -> Result<Option<UpdateInfo>, String> {
    // deb installs cannot self-update (the updater swaps the appimage
    // binary in place); report "no update" rather than offering one
    // that would fail mid-install. releases page covers deb users.
    #[cfg(target_os = "linux")]
    if std::env::var_os("APPIMAGE").is_none() {
        return Ok(None);
    }

    use tauri_plugin_updater::UpdaterExt;
    let updater = app.updater().map_err(|e| e.to_string())?;
    match updater.check().await {
        Ok(Some(update)) => {
            let info = UpdateInfo {
                version: update.version.clone(),
                notes: update.body.clone(),
            };
            if let Some(state) = app.try_state::<PendingUpdate>() {
                if let Ok(mut guard) = state.0.lock() {
                    *guard = Some(update);
                }
            }
            Ok(Some(info))
        }
        Ok(None) => Ok(None),
        // offline is normal for a field laptop — a failed check is
        // "no update right now", never an error surface.
        Err(e) => {
            eprintln!("[loom] update check failed: {e}");
            Ok(None)
        }
    }
}

// ipc command: download + install the update the operator consented
// to, then relaunch. the sidecar is stopped FIRST — nsis cannot
// replace a running exe, and a live sqlite writer must not be killed
// mid-transaction by an installer.
#[tauri::command]
async fn install_update(app: AppHandle) -> Result<(), String> {
    let update = app
        .try_state::<PendingUpdate>()
        .and_then(|state| {
            state.0.lock().ok().and_then(|mut guard| guard.take())
        })
        .ok_or_else(|| "no update pending — check again".to_string())?;

    graceful_shutdown_sidecar_async(&app).await;

    update
        .download_and_install(|_, _| {}, || {})
        .await
        .map_err(|e| format!("update install failed: {e}"))?;
    app.restart()
}

// ipc command: bundle the shell log dir, the backend's lite log dir
// and a version manifest into a user-chosen zip for support requests.
// returns the saved path, or None when the user cancels the dialog.
//
// the allowlist inside build_diagnostics_zip is load-bearing: the
// export must never include the database, buckets/ evidence or
// secrets.json. backend log lines are already redacted at write time
// by the sidecar's log pipeline, so no re-redaction happens here.
#[tauri::command]
async fn export_diagnostics(
    app: AppHandle,
) -> Result<Option<String>, String> {
    // the dialog plugin's ``save_file`` uses a callback; wrap it in a
    // oneshot so the async command can await the user's choice.
    let (tx, rx) = tokio::sync::oneshot::channel();
    app.dialog()
        .file()
        .set_file_name("loom-diagnostics.zip")
        .add_filter("zip archive", &["zip"])
        .save_file(move |path| {
            let _ = tx.send(path);
        });
    let picked = rx
        .await
        .map_err(|e| format!("save dialog channel closed: {e}"))?;
    let Some(picked) = picked else {
        return Ok(None);
    };
    let dest = picked.into_path().map_err(|e| e.to_string())?;

    let shell_logs = app.path().app_log_dir().ok();
    let backend_logs = load_config(&app)?.resolve_data_dir().join("logs");
    let version = app.package_info().version.to_string();

    // zip assembly is blocking file io; keep it off the async runtime.
    let zip_dest = dest.clone();
    tauri::async_runtime::spawn_blocking(move || {
        build_diagnostics_zip(&zip_dest, shell_logs, &backend_logs, &version)
    })
    .await
    .map_err(|e| format!("diagnostics task failed: {e}"))??;

    Ok(Some(dest.display().to_string()))
}

fn build_diagnostics_zip(
    dest: &Path,
    shell_logs: Option<PathBuf>,
    backend_logs: &Path,
    version: &str,
) -> Result<(), String> {
    use std::io::Write;

    let file = std::fs::File::create(dest)
        .map_err(|e| format!("cannot create {}: {e}", dest.display()))?;
    let mut zip = zip::ZipWriter::new(file);
    let options = zip::write::SimpleFileOptions::default();

    // strict allowlist — exactly these three entries, nothing else:
    //   1. shell log dir (tauri-plugin-log files + crash files)
    //   2. backend lite log dir (redacted jsonl)
    //   3. a generated manifest.txt
    if let Some(dir) = shell_logs {
        add_dir_files(&mut zip, &dir, "shell-logs", dest, options)?;
    }
    add_dir_files(&mut zip, backend_logs, "backend-logs", dest, options)?;

    zip.start_file("manifest.txt", options)
        .map_err(|e| e.to_string())?;
    let manifest = format!(
        "loom-desktop {version}\nos: {} {}\nexported-unix: {}\n",
        std::env::consts::OS,
        std::env::consts::ARCH,
        unix_now(),
    );
    zip.write_all(manifest.as_bytes())
        .map_err(|e| e.to_string())?;
    zip.finish().map_err(|e| e.to_string())?;
    Ok(())
}

// adds the plain files of ``dir`` under ``prefix/`` in the zip. never
// recurses: the allowlist is exactly "log files in this directory".
// ``skip`` excludes the zip being written, in case the user saves it
// into one of the log directories.
fn add_dir_files(
    zip: &mut zip::ZipWriter<std::fs::File>,
    dir: &Path,
    prefix: &str,
    skip: &Path,
    options: zip::write::SimpleFileOptions,
) -> Result<(), String> {
    let entries = match std::fs::read_dir(dir) {
        Ok(entries) => entries,
        // a missing dir just means nothing was logged yet.
        Err(_) => return Ok(()),
    };
    for entry in entries.flatten() {
        let path = entry.path();
        if !path.is_file() || path == skip {
            continue;
        }
        let Some(name) = path.file_name().and_then(|n| n.to_str()) else {
            continue;
        };
        zip.start_file(format!("{prefix}/{name}"), options)
            .map_err(|e| e.to_string())?;
        let mut src = std::fs::File::open(&path)
            .map_err(|e| format!("cannot read {}: {e}", path.display()))?;
        std::io::copy(&mut src, zip).map_err(|e| e.to_string())?;
    }
    Ok(())
}

fn main() {
    tauri::Builder::default()
        .plugin(tauri_plugin_shell::init())
        .plugin(tauri_plugin_dialog::init())
        .plugin(tauri_plugin_fs::init())
        .plugin(tauri_plugin_store::Builder::default().build())
        .plugin(tauri_plugin_updater::Builder::new().build())
        .plugin(tauri_plugin_process::init())
        // rotating shell logs in the platform log dir plus stdout for
        // `tauri dev`. sidecar output reaches these files through the
        // drain in spawn_backend. size-capped: 5 mb per file, newest
        // five files kept.
        .plugin(
            tauri_plugin_log::Builder::new()
                .targets([
                    Target::new(TargetKind::Stdout),
                    Target::new(TargetKind::LogDir { file_name: None }),
                ])
                .level(log::LevelFilter::Info)
                .max_file_size(5 * 1024 * 1024)
                .rotation_strategy(RotationStrategy::KeepSome(5))
                .build(),
        )
        .manage(SidecarProcess(Mutex::new(None)))
        .manage(LastBackendStderr::default())
        .manage(BootReady::default())
        .manage(PendingUpdate(Mutex::new(None)))
        .invoke_handler(tauri::generate_handler![
            pick_directory,
            disk_usage,
            persist_data_directory,
            restart_backend,
            factory_reset,
            check_for_update,
            install_update,
            export_diagnostics,
        ])
        .setup(|app| {
            let handle = app.handle().clone();

            // install panic + signal handlers before spawning the
            // sidecar so they cover bootstrap failures too.
            install_panic_hook(handle.clone());
            install_signal_handlers(handle.clone());

            // windows-only: create the job object that will hold every
            // sidecar bootloader spawned during this app lifetime.
            // closing the handle (which happens automatically on
            // process exit) cascades termination to all in-job
            // processes via JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE.
            #[cfg(windows)]
            {
                match sidecar_job::create() {
                    Ok(job) => {
                        app.manage(job);
                    }
                    Err(err) => {
                        eprintln!(
                            "[loom] could not create sidecar job object: {err}"
                        );
                    }
                }
            }

            let secrets = ensure_bootstrap_secrets(&handle)
                .map_err(|e| -> Box<dyn std::error::Error> { e.into() })?;
            app.manage(BackendState(Mutex::new(secrets.clone())));

            // boot the sidecar on the async runtime so the setup
            // closure returns immediately; the os never sees the
            // main thread block and the webview opens on its normal
            // schedule. the boot-gate ui sits on ``booting`` until
            // the watcher emits ``backend-ready`` or
            // ``backend-error``.
            let boot_handle = handle.clone();
            tauri::async_runtime::spawn(async move {
                run_initial_boot(boot_handle).await;
            });
            Ok(())
        })
        .on_window_event(|window, event| {
            if let WindowEvent::CloseRequested { .. } = event {
                graceful_shutdown_sidecar(window.app_handle());
            }
        })
        .build(tauri::generate_context!())
        .expect("error while building tauri application")
        .run(|app_handle, event| {
            // final safety net: cover exit paths that bypass the
            // window CloseRequested handler (RunEvent::Exit fires on
            // normal shutdown; ExitRequested fires when app.exit()
            // is called from a signal handler).
            if matches!(
                event,
                RunEvent::Exit | RunEvent::ExitRequested { .. }
            ) {
                graceful_shutdown_sidecar(app_handle);
            }
        });
}

#[cfg(windows)]
mod sidecar_job {
    //! windows job object that owns every sidecar bootloader spawned
    //! during the lifetime of the tauri shell.
    //!
    //! created once at app setup and tucked into tauri state. each
    //! sidecar pid is assigned to the job after spawn. when the tauri
    //! process exits — for any reason, including SIGKILL, force-quit,
    //! or an unhandled panic — the os closes the job handle, which
    //! triggers JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE and terminates
    //! every process still in the job. that covers the pyinstaller
    //! --onefile orphan case (bootloader -> python child) without
    //! relying on cooperation from either process.

    use std::mem::MaybeUninit;

    use windows_sys::Win32::Foundation::{CloseHandle, HANDLE};
    use windows_sys::Win32::System::JobObjects::{
        AssignProcessToJobObject, CreateJobObjectW,
        JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE,
        JOBOBJECT_EXTENDED_LIMIT_INFORMATION, JobObjectExtendedLimitInformation,
        SetInformationJobObject,
    };
    use windows_sys::Win32::System::Threading::{
        OpenProcess, PROCESS_SET_QUOTA, PROCESS_TERMINATE,
    };

    // BOOL in windows-sys is a plain i32 alias and FALSE is 0. avoid
    // depending on the FALSE constant's import location (it has moved
    // between minor releases of the crate) by spelling it as the
    // literal where required.
    const FALSE_BOOL: i32 = 0;

    pub struct JobHandle(HANDLE);

    // HANDLE is a raw pointer alias; the kernel object behind it is
    // refcounted and thread-safe. assigning processes from any thread
    // is supported and the only mutation we perform.
    unsafe impl Send for JobHandle {}
    unsafe impl Sync for JobHandle {}

    impl Drop for JobHandle {
        fn drop(&mut self) {
            if !self.0.is_null() {
                // closing the last handle to a job with the
                // KILL_ON_JOB_CLOSE limit terminates every process in
                // it. that's the whole point — this is what cleans up
                // orphaned sidecars on app exit.
                unsafe {
                    CloseHandle(self.0);
                }
            }
        }
    }

    pub fn create() -> Result<JobHandle, String> {
        let raw = unsafe { CreateJobObjectW(std::ptr::null(), std::ptr::null()) };
        if raw.is_null() {
            return Err("CreateJobObjectW returned null".into());
        }

        let mut info: JOBOBJECT_EXTENDED_LIMIT_INFORMATION =
            unsafe { MaybeUninit::zeroed().assume_init() };
        info.BasicLimitInformation.LimitFlags =
            JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE;

        let ok = unsafe {
            SetInformationJobObject(
                raw,
                JobObjectExtendedLimitInformation,
                &info as *const JOBOBJECT_EXTENDED_LIMIT_INFORMATION
                    as *const std::ffi::c_void,
                std::mem::size_of::<JOBOBJECT_EXTENDED_LIMIT_INFORMATION>()
                    as u32,
            )
        };
        if ok == 0 {
            unsafe {
                CloseHandle(raw);
            }
            return Err(
                "SetInformationJobObject failed for KILL_ON_JOB_CLOSE".into(),
            );
        }

        Ok(JobHandle(raw))
    }

    pub fn assign(job: &JobHandle, pid: u32) -> Result<(), String> {
        let process = unsafe {
            OpenProcess(
                PROCESS_TERMINATE | PROCESS_SET_QUOTA,
                FALSE_BOOL,
                pid,
            )
        };
        if process.is_null() {
            return Err(format!("OpenProcess({pid}) returned null"));
        }
        let ok = unsafe { AssignProcessToJobObject(job.0, process) };
        unsafe {
            CloseHandle(process);
        }
        if ok == 0 {
            return Err(format!("AssignProcessToJobObject({pid}) failed"));
        }
        Ok(())
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::fs;
    use tempfile::tempdir;

    fn touch(path: &Path) {
        if let Some(parent) = path.parent() {
            fs::create_dir_all(parent).unwrap();
        }
        fs::write(path, b"placeholder").unwrap();
    }

    #[test]
    fn purge_removes_known_artefacts() {
        let dir = tempdir().unwrap();
        let root = dir.path();
        touch(&root.join("loom.db"));
        touch(&root.join("loom.db-wal"));
        touch(&root.join("loom.db-shm"));
        touch(&root.join("buckets/loom-originals/case-a/asset.bin"));
        touch(&root.join("buckets/loom-derivatives/case-a/thumb.jpg"));

        purge_lite_data(root).expect("purge should succeed");

        assert!(!root.join("loom.db").exists());
        assert!(!root.join("loom.db-wal").exists());
        assert!(!root.join("loom.db-shm").exists());
        assert!(!root.join("buckets").exists());
    }

    #[test]
    fn purge_leaves_unrelated_files_alone() {
        // anything the user dropped in by hand stays put. only the
        // hard-coded PURGE_FILES + PURGE_DIRS are touched.
        let dir = tempdir().unwrap();
        let root = dir.path();
        touch(&root.join("loom.db"));
        touch(&root.join("user-notes.txt"));
        touch(&root.join("photos/family.jpg"));

        purge_lite_data(root).expect("purge should succeed");

        assert!(!root.join("loom.db").exists());
        assert!(root.join("user-notes.txt").exists());
        assert!(root.join("photos/family.jpg").exists());
    }

    #[test]
    fn purge_is_noop_when_data_dir_missing() {
        // never-completed first-run: data_dir doesn't exist yet.
        // factory_reset must still succeed so the caller can move on
        // to clearing the preference and respawning the sidecar.
        let dir = tempdir().unwrap();
        let missing = dir.path().join("never-created");
        assert!(!missing.exists());

        purge_lite_data(&missing).expect("missing dir should be a no-op");
    }

    #[test]
    fn purge_is_idempotent() {
        // second invocation after a successful purge must not error
        // on already-missing artefacts.
        let dir = tempdir().unwrap();
        let root = dir.path();
        touch(&root.join("loom.db"));
        touch(&root.join("buckets/loom-originals/case-a/asset.bin"));

        purge_lite_data(root).expect("first purge");
        purge_lite_data(root).expect("second purge should be idempotent");
    }

    #[test]
    fn resolve_data_dir_uses_the_persisted_directory() {
        // a respawn after the first-run data-dir switch must target the
        // chosen directory, so the bootstrap admin lands in the final db.
        let chosen = PathBuf::from("/mnt/evidence/loom");
        let config = LoomConfig {
            data_dir: Some(chosen.clone()),
        };
        assert_eq!(config.resolve_data_dir(), chosen);
    }

    #[test]
    fn resolve_data_dir_falls_back_to_dot_loom() {
        // first launch before any directory is chosen.
        let config = LoomConfig { data_dir: None };
        assert!(config.resolve_data_dir().ends_with(".loom/data"));
    }
}
