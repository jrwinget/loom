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
   password is hashed with argon2 and stored in the local database.
4. **Save your recovery codes** — eight single-use codes are minted
   alongside the admin and shown exactly once. Store them in a
   password manager (or download the .txt). Each code can reset your
   password once if you forget it; once all eight are spent, the
   only path back in is a factory reset (see below).

After these four screens, Loom opens the main case workspace.

## Quick start

A short orientation for your first session. If you have not installed Loom
yet, download the installer for your platform from the
[releases page](https://github.com/jrwinget/loom/releases) and work through
[Installing](#installing) and [First run](#first-run) first.

Once you sign in, Loom opens on your case workspace. The left sidebar is how
you move around — **Dashboard**, **Cases**, **Settings**, and (on Desktop
Lite) **Storage**. The button in the top-right corner shows your account
initial; click it for **Settings** and **Logout**. Press `?` at any time to
see the full list of keyboard shortcuts.

A typical first session:

1. **Create a case.** Go to **Cases** and click **Create Case**. A case is
   the container for one investigation — give it a name and an optional
   description, then open it to reach the case workspace.
2. **Add evidence.** Inside the case, open **Assets** and add material two
   ways: drag video, image, or document files onto the upload area, or paste a
   link to capture online media (Loom downloads it and, best-effort, requests a
   web-archive snapshot). Every original is hashed and stored read-only for
   chain of custody — see [Data directory](#data-directory). Ingest runs in the
   background, so large files keep processing while you work.
3. **Review and annotate.** Open an asset to scrub playback, read its
   transcript, search within it, and mark observations, claims, and disputes.
   Playback has its own shortcuts (`Space` to play/pause, arrows to skip,
   `I` / `O` to mark in and out points) — press `?` for the full set.
4. **Build the timeline.** Open **Timeline** to place events on a shared
   clock. Loom proposes correlations between assets; use the confidence slider
   to tighten or loosen which matches it surfaces. **Conflicts**, **Clusters**,
   and **Map** (in the sidebar while a case is open) offer complementary views
   of the same evidence.
5. **Export for court.** Open **Export** to produce a signed court bundle (a
   `.loom` archive) containing the originals, derivatives, annotations,
   timeline, and chain of custody. The bundle is hash-verified on import, so it
   can be handed to another Loom install or a server deploy without losing
   provenance.

### Staying secure

The eight recovery codes from first run are the only way back in if you
forget your password (see [Forgot your password?](#forgot-your-password)), so
keep them somewhere safe. You can add a second factor under your account's
**Settings → Security**.

### Getting help

Found a bug or have a question? Open an issue at
<https://github.com/jrwinget/loom/issues>. For anything security-sensitive,
follow the responsible-disclosure process in [security.md](security.md) rather
than filing a public issue.

## Forgot your password?

If you have at least one unused recovery code:

1. From the sign-in screen, click **Forgot your password?**.
2. Enter your email, one recovery code, and a new password.
3. Sign in normally with the new password. Any MFA enrollment is
   unaffected — the code resets the password only.

If you have lost both the password and every recovery code, the
only path forward is a destructive reset. From the sign-in screen
click **Reset Loom (deletes all data)** — this is only visible inside
the Desktop Lite shell. The confirmation dialog requires you to type
`RESET` and lists exactly what gets deleted: the SQLite database,
all originals and derivatives, and your chosen data-directory
preference. Bootstrap secrets are preserved. After the reset, Loom
re-runs the first-run wizard.

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

## Boot sequence

On launch, Loom opens its window immediately and shows a "Loom is
starting…" panel while the local backend boots in the background.
The panel transitions to the app within a few seconds on Linux and
macOS; Windows cold-start can take up to ~10 seconds the first
time after install because antivirus rescans the PyInstaller
payload. After the first launch, subsequent starts are faster.

If the backend cannot start, the panel switches to an error view
with the sidecar's captured stderr and a Retry button. Retry kills
the current sidecar and respawns it; the panel returns to "Loom is
starting…" until the next outcome.

## Troubleshooting

**The app stays on "Loom is starting…" forever.**
The sidecar binary is alive but `127.0.0.1:8000` never answers.
Most common cause is a port conflict — quit whatever else is using
that port and click Retry. If the boot panel does not appear and
the app window itself never opens, the desktop shell crashed
before mounting; see the system journal (`journalctl --user`) on
Linux or Event Viewer on Windows.

**The boot panel switches to an error view.**
Read the captured stderr in the panel; that line is the sidecar's
own diagnosis. The full log lives at:

- macOS/Linux: `~/.loom/logs/backend.log`
- Windows: `%USERPROFILE%\.loom\logs\backend.log`

A common case is `LOOM_DATABASE_URL` pointing at a path Loom cannot
write to (read-only mount, missing parent directory). Pick a fresh
data directory via Settings → Storage or delete `~/.loom/config.json`
and relaunch to re-run the first-run picker.

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
- The one exception is URL ingestion: when you explicitly submit a
  URL via the ingest form, Loom fetches that URL and (best-effort)
  requests a Wayback Machine snapshot. Depending on the URL, this
  may contact YouTube / Twitter / other sites (via yt-dlp),
  archive.org, or the submitted host directly. No outbound traffic
  is generated unless you submit a URL; the dispatcher also blocks
  URLs that resolve to private / loopback / link-local addresses.
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
