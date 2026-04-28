//! Tauri shell — spawns the Python sim API as a sidecar child process
//! on startup, exposes the resolved base URL to the frontend via
//! `invoke('get_api_base')`, and tears the child down on app exit.
//!
//! Why this lives here:
//!   - "App = one click" was a real complaint (2026-04-26 audit).
//!   - The dashboard previously required THREE manual launches:
//!       (1) ollama serve  (2) lw serve  (3) npm run tauri dev
//!     This module collapses (2) into (3). Ollama remains separate
//!     because it's an independent product that we don't ship.
//!
//! Dev mode (`npm run tauri dev`):
//!   The sidecar runs uvicorn on `living_world.web.server:app` from the
//!   workspace venv. Python interpreter resolution order:
//!     1. $LW_PYTHON env var (escape hatch for advanced users)
//!     2. ../.venv/bin/python                  (POSIX venv)
//!     3. ..\.venv\Scripts\python.exe          (Windows venv)
//!     4. system `python3` (last resort)
//!
//! Production mode (`tauri build`): see L-21 — needs PyInstaller to
//! produce a single Python binary that ships in `bundle.externalBin`.
//! The dev path here is structurally identical: spawn child, wait for
//! /api/health, expose base URL, kill on exit.
//!
//! Lifecycle limitation (also tracked in L-21):
//!   `kill_on_drop(true)` sends SIGKILL when tokio drops the Child
//!   handle — which only happens on graceful parent exit. If Tauri
//!   itself is SIGKILL'd (or crashes), the Python child orphans and
//!   keeps :8765 bound until manually reaped. Production fix: put the
//!   child in its own POSIX process group via setpgid() (or a Windows
//!   job object) so the kernel reaps it when the parent dies.

use std::path::PathBuf;
use std::process::Stdio;
use std::sync::Mutex;
use std::time::Duration;

use tauri::{AppHandle, Manager, State};
use tokio::process::{Child, Command};

const SIDECAR_PORT: u16 = 8765;
const HEALTH_TIMEOUT_SECS: u64 = 30;

/// App-wide handle to the running Python sidecar + its base URL. The
/// child lives until app exit; the URL is read by the frontend on
/// startup via `invoke('get_api_base')`.
#[derive(Default)]
pub struct SidecarState {
    pub child: Mutex<Option<Child>>,
    pub api_base: Mutex<Option<String>>,
}

/// Frontend reads this at boot so it doesn't have to know which port
/// the sidecar landed on. Returns `None` until the sidecar is healthy.
#[tauri::command]
fn get_api_base(state: State<'_, SidecarState>) -> Option<String> {
    state.api_base.lock().ok().and_then(|g| g.clone())
}

/// Resolve which executable spawns the sim API.
///
/// Production (`tauri build`): prefer the PyInstaller-bundled binary
/// next to the app executable. Tauri's `bundle.externalBin` ships the
/// platform-specific `lw-sidecar-<triple>{.exe}` alongside Tauri's own
/// binary; the OS resolves it via $PATH at launch time.
///
/// Dev (`tauri dev`): fall back to `python -m living_world.web` from
/// the workspace venv. This avoids the multi-minute PyInstaller round-
/// trip every time we touch a Python file.
///
/// Returns (executable_path, prefix_args). The `--module` form is the
/// dev path; production passes no extra args because the binary is
/// already a Python entry point.
fn resolve_sidecar_command() -> (PathBuf, Vec<String>) {
    // Manual override always wins (useful for CI / debugging).
    if let Ok(p) = std::env::var("LW_PYTHON") {
        return (PathBuf::from(p), vec!["-m".into(), "living_world.web".into()]);
    }
    // Production binary check: Tauri places externalBin next to the
    // running executable. We can't ask Tauri for the resource path
    // synchronously here, so probe relative to current_exe.
    if let Ok(exe) = std::env::current_exe() {
        if let Some(dir) = exe.parent() {
            #[cfg(target_os = "windows")]
            let bin_name = "lw-sidecar.exe";
            #[cfg(not(target_os = "windows"))]
            let bin_name = "lw-sidecar";
            let bundled = dir.join(bin_name);
            if bundled.exists() {
                return (bundled, vec![]);
            }
        }
    }
    // Dev fallback: project venv.
    let manifest = PathBuf::from(env!("CARGO_MANIFEST_DIR"));
    let repo_root = manifest.parent().and_then(|p| p.parent()).unwrap_or(&manifest);
    let posix = repo_root.join(".venv/bin/python");
    if posix.exists() {
        return (posix, vec!["-m".into(), "living_world.web".into()]);
    }
    let windows = repo_root.join(".venv/Scripts/python.exe");
    if windows.exists() {
        return (windows, vec!["-m".into(), "living_world.web".into()]);
    }
    (PathBuf::from("python3"), vec!["-m".into(), "living_world.web".into()])
}

async fn wait_for_port(host: &str, port: u16) -> bool {
    // Uvicorn binds the listening socket AFTER FastAPI app construction
    // succeeds, so a TCP-connect probe is sufficient — no HTTP client
    // dependency needed. (Verified by reading uvicorn's startup sequence:
    // `Server.startup()` fires lifespan events first, then `_serve()`
    // creates the socket.)
    let addr = format!("{host}:{port}");
    let deadline = std::time::Instant::now() + Duration::from_secs(HEALTH_TIMEOUT_SECS);
    while std::time::Instant::now() < deadline {
        if tokio::net::TcpStream::connect(&addr).await.is_ok() {
            return true;
        }
        tokio::time::sleep(Duration::from_millis(250)).await;
    }
    false
}

async fn spawn_sidecar(app: AppHandle) -> Result<(), String> {
    let (executable, args) = resolve_sidecar_command();
    let manifest = PathBuf::from(env!("CARGO_MANIFEST_DIR"));
    let repo_root = manifest.parent().and_then(|p| p.parent()).unwrap_or(&manifest);

    eprintln!("[sidecar] executable: {}", executable.display());
    eprintln!("[sidecar] args:       {:?}", args);
    eprintln!("[sidecar] cwd:        {}", repo_root.display());
    eprintln!("[sidecar] port:       {}", SIDECAR_PORT);

    let child = Command::new(&executable)
        .args(&args)
        // Both dev (python -m) and prod (PyInstaller binary) read the
        // same env vars; see living_world/web/__main__.py.
        .env("LW_API_HOST", "127.0.0.1")
        .env("LW_API_PORT", SIDECAR_PORT.to_string())
        .env("LW_API_LOG_LEVEL", "warning")
        .current_dir(repo_root)
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .kill_on_drop(true)
        .spawn()
        .map_err(|e| format!("failed to spawn sidecar ({}): {e}", executable.display()))?;

    // Stash the child immediately so we can kill it even if /api/health never lands.
    let state = app.state::<SidecarState>();
    *state.child.lock().unwrap() = Some(child);

    let base = format!("http://127.0.0.1:{SIDECAR_PORT}");
    let healthy = wait_for_port("127.0.0.1", SIDECAR_PORT).await;
    if !healthy {
        return Err(format!(
            "sidecar /api/health did not reach 200 within {HEALTH_TIMEOUT_SECS}s — \
             check that `make install` has been run and that port {SIDECAR_PORT} is free"
        ));
    }
    *state.api_base.lock().unwrap() = Some(base.clone());
    eprintln!("[sidecar] healthy at {base}");
    Ok(())
}

fn kill_sidecar(state: &SidecarState) {
    if let Ok(mut guard) = state.child.lock() {
        if let Some(mut child) = guard.take() {
            // start_kill is non-blocking; on Drop the OS reaps the process.
            let _ = child.start_kill();
        }
    }
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_opener::init())
        .manage(SidecarState::default())
        .setup(|app| {
            let handle = app.handle().clone();
            tauri::async_runtime::spawn(async move {
                if let Err(e) = spawn_sidecar(handle).await {
                    eprintln!("[sidecar] startup failed: {e}");
                    // Window still loads; api.ts will fall back to localhost:8000
                    // (legacy port) so a manual `lw serve` still works for power users.
                }
            });
            Ok(())
        })
        .on_window_event(|window, event| {
            if let tauri::WindowEvent::Destroyed = event {
                kill_sidecar(&window.state::<SidecarState>());
            }
        })
        .invoke_handler(tauri::generate_handler![get_api_base])
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
