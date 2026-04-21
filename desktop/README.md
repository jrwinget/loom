# Loom Desktop Shell

A Tauri v2 desktop wrapper around the Loom evidence OS. This package
produces a double-clickable installer (`.dmg`, `.msi`, `.AppImage`,
`.deb`) that ships the Python backend as a sidecar binary and loads
the compiled frontend inside a native WebView.

The shell exists so that National Lawyers Guild legal observers can
install Loom on a field laptop without touching Docker, Postgres, or
the terminal.

## Prerequisites

- Rust toolchain (stable) with `cargo` on `PATH`
- `@tauri-apps/cli` v2 (installed as a devDependency of this package)
- Platform build dependencies for Tauri v2. See the Tauri v2 guide:
  <https://v2.tauri.app/start/prerequisites/>
  - **macOS**: Xcode Command Line Tools
  - **Linux**: `libwebkit2gtk-4.1-dev`, `libssl-dev`, `libayatana-
    appindicator3-dev`, `librsvg2-dev`, `patchelf`
  - **Windows**: WebView2 runtime (shipped with Windows 11; installer
    redistributable for Windows 10)
- A built frontend at `../frontend/dist` (run `pnpm build` in
  `frontend/` first)
- A packaged backend sidecar at `../backend/dist/loom-backend`. The
  CI pipeline produces this via PyInstaller; for local dev runs you
  can symlink a shell script that execs `uv run uvicorn`.

## Developer workflow

```bash
# from repo root
cd frontend && pnpm build && cd ..
# build backend sidecar (CI does this via PyInstaller; local devs
# typically run the backend separately and skip this step)

cd desktop
pnpm install
pnpm dev          # launches tauri with hot-reload at :3000
```

`pnpm dev` expects the frontend dev server to be running at
`http://127.0.0.1:3000`. The Rust shell will launch the sidecar, wait
for `http://127.0.0.1:8000/api/v1/health` to return 200, then load the
WebView.

## Producing an unsigned local build

```bash
pnpm build:unsigned
```

Artifacts land in `src-tauri/target/release/bundle/`. These builds are
unsigned and will trip Gatekeeper on macOS and SmartScreen on Windows
until the CI pipeline applies real signatures.

## Gotchas

- **Signing is deferred to CI.** Do not attempt to sign locally. The
  Apple notarization flow and the Windows EV certificate live in the
  release workflow; local signing produces artifacts that confuse
  end-users when they don't match the published hashes.
- **Bundle identifiers are load-bearing.** Keep `org.nlg.loom` stable
  across releases; changing it breaks auto-update on macOS.
- **Sidecar architecture matching.** The PyInstaller backend is
  built per-arch (arm64 / x86_64). Tauri expects the sidecar binary
  to exist at `backend/dist/loom-backend-<triple>` at bundle time;
  see the Tauri v2 sidecar docs.
- **Lite profile is mandatory here.** The desktop shell always
  launches the backend with `LOOM_DEPLOYMENT_PROFILE=lite`. Do not
  add a toggle; field laptops never run the server profile.
- **Data directory is user-chosen on first run.** The dialog plugin
  opens a folder picker; the chosen path is persisted via the Tauri
  store and passed as `LOOM_DATA_DIR` on every subsequent launch.
- **Icons are placeholders.** Drop real assets into
  `src-tauri/icons/` before cutting a release. See the README in
  that directory for the expected filenames.
