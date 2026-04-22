# Loom Desktop Lite

## Overview

Desktop Lite is a single-user, local-only install of Loom intended for
legal observers and attorneys who need to build an evidence timeline on
a field laptop without running a server. Everything stays on the
device: originals, derivatives, database, and logs. Nothing leaves the
machine unless you explicitly export it.

## Installing

Each release publishes unsigned installers for Windows, macOS, and
Linux. Download the one matching your operating system from the
release page.

### Windows

Double-click the `.msi` (recommended) or the `.exe` (NSIS installer)
and follow the prompts. Windows may display "Windows protected your
PC" or warn about an unknown publisher. That warning is expected
until the EV certificate is in place. To proceed:

1. Click **More info**.
2. Click **Run anyway**.

The MSI installs into `C:\Program Files\Loom` by default.

### macOS

1. Open the `.dmg`.
2. Drag **Loom.app** into the **Applications** folder.
3. The first time you launch, Gatekeeper will block the app because
   it is not yet notarized. Right-click **Loom.app** and choose
   **Open**, then confirm **Open** in the dialog. This only needs to
   be done once per install. Double-click works normally after that.

Notarization will remove this step; until then, the right-click bypass
is the supported workflow.

### Linux

Two formats are shipped:

```bash
# debian / ubuntu
sudo dpkg -i loom_*.deb

# any distro, no root
chmod +x Loom_*.AppImage
./Loom_*.AppImage
```

The `.deb` installs a desktop entry; the AppImage is self-contained
and can live anywhere on disk.

## First run

On first launch Loom walks through three screens:

1. **Welcome** — confirms this is a local-only install and that no
   data will be sent anywhere.
2. **Pick data directory** — choose where originals, derivatives, and
   the SQLite database should live. The default is `~/.loom/data`
   (Windows: `%USERPROFILE%\.loom\data`). Pick a directory on a disk
   with room for the footage you plan to ingest. This path is
   remembered across launches.
3. **Create admin account** — sets up the single local user. The
   password is hashed with argon2 and stored in the local database;
   there is no password reset over network, so write it down.

After these three screens, Loom opens the main case workspace.

## What Desktop Lite does vs what it does NOT

Desktop Lite:

- Runs as a single user on one machine.
- Uses SQLite as the database (file: `loom.db` in the data
  directory).
- Stores files on the local filesystem under the data directory.
- Runs workers in-process — no Temporal server, no Redis, no Docker.
- Supports ingest, timeline synthesis, annotations, chain of custody,
  and court-bundle export.

Desktop Lite does **not** support:

- Multi-user collaboration or concurrent editing.
- Organizations, teams, or shared case membership.
- Shared evidence links between users.
- The plugin marketplace.
- Any feature that depends on Temporal, Postgres, or a shared
  object store.

If you need any of those, run the server deploy (see `deployment.md`)
instead. Desktop Lite can import from and export to a server deploy
via the court-bundle format — see below.

## Data directory

Everything Loom writes lives under the data directory you chose on
first run. The layout is:

```
<data_dir>/
  loom.db                    # sqlite database
  buckets/
    loom-originals/          # immutable originals (WORM)
    loom-derivatives/        # proxies, transcripts, thumbnails
  logs/
    backend.log              # backend process log
```

Files inside `buckets/loom-originals/` are marked read-only (OS
read-only flag) immediately after write. This preserves WORM evidence
semantics: the operating system will refuse to overwrite an original
asset even if a process tries. Derivatives are writable because they
can be regenerated.

Do not move, rename, or edit files inside `buckets/` by hand. Loom
keeps hashes and chain-of-custody entries that will flag any
tampering.

## Importing from / exporting to the server deploy

Court-bundle export works bi-directionally:

- **Export** from Desktop Lite: Case → Export produces a signed
  bundle (`.loom` archive) containing assets, derivatives,
  annotations, timeline, and chain-of-custody. The bundle can be
  imported into a server deploy.
- **Import** on Desktop Lite: drag a `.loom` bundle onto the Loom
  window or use Case → Import. Hashes are verified on import; any
  mismatch aborts the import and reports the offending asset.

For the exact bundle schema and verification procedure, see
`docs/architecture.md` (export section) — the dedicated
court-bundle spec document is a follow-up.

## Troubleshooting

**The app opens but the UI shows "backend unreachable".**
The backend sidecar failed to start. Check the log at:

- macOS/Linux: `~/.loom/logs/backend.log`
- Windows: `%USERPROFILE%\.loom\logs\backend.log`

The most common cause is a port conflict on `127.0.0.1:8000`. Quit
whatever else is using that port, then relaunch.

**First run fails with "permission denied" on the data directory.**
The user account running Loom does not have write access to the
path you picked. Choose a directory under your home folder, or `chmod`
the directory so your user can write to it.

**I want to start over.**
Quit Loom, delete the data directory (`~/.loom/data` by default),
and relaunch. The welcome flow will run again. This destroys all
cases and originals on that device — there is no undo.

**Ingest jobs get stuck.**
Workers run in-process; if the app was force-quit mid-ingest, restart
Loom and the ingest will resume from its last checkpoint. If a job
stays stuck past a restart, the log file will show which activity is
failing.

## Security model

Desktop Lite is local-only by design:

- The backend binds to `127.0.0.1` only. There is no listener on
  any external interface; other machines on the same network cannot
  reach it.
- No outbound network calls are made by Loom itself. Update checks,
  telemetry, and crash reporting are off.
- Originals are stored read-only via the OS read-only flag, giving
  WORM semantics without a dedicated object store.
- Authentication, session management, and CSRF protection use the
  same JWT + argon2 + double-submit stack as the server deploy, so
  if you later migrate to the server, your security posture is
  consistent.
- No face recognition, no suspicion scoring, and no automated
  identity resolution are performed. These are non-negotiable
  project principles regardless of deployment mode.

### Bootstrap secrets

On first run the Tauri shell generates two cryptographically random
32-byte secrets and persists them via `tauri-plugin-store`:

- `LOOM_SECRET_KEY` — signs JWT access and refresh tokens.
- `LOOM_STORAGE_SIGNING_SECRET` — signs the loopback presigned URLs
  used by the in-process storage backend.

Both are unique per install (two installs on the same machine do
not share either secret) and are read back on every subsequent
launch so sessions and stored URLs remain valid. The secrets never
leave the machine and never appear in logs. To rotate them, quit
Loom and delete `secrets.json` from the Tauri app-data directory;
the next launch will regenerate both and invalidate any URL / token
signed by the old values.
