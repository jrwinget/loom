# Loom

[![CI](https://github.com/jrwinget/loom/actions/workflows/ci.yml/badge.svg)](https://github.com/jrwinget/loom/actions/workflows/ci.yml)
[![Desktop](https://github.com/jrwinget/loom/actions/workflows/desktop.yml/badge.svg)](https://github.com/jrwinget/loom/actions/workflows/desktop.yml)

**An evidence operating system for civil-rights legal teams.**

Loom helps legal observers, civil-rights attorneys, and movement lawyers turn
raw field evidence (e.g., body-cam footage, bystander video, photos, audio,
statements, FOIA returns) into a defensible event timeline where every claim
traces back to source material. It's civil-liberties tooling, not surveillance
tech: there is no face recognition, no suspicion scoring, and no automated
identity resolution.

> **Project status: beta.** Loom is being prepared for first production use in
> Cook County, Illinois (state and federal § 1983 actions). The Desktop Lite
> installer is the supported path for individual practitioners; the server
> deploy is for organizations that need shared cases. See
> [`docs/requirements.md`](docs/requirements.md) for the jurisdictional,
> hardware, and compliance defaults the beta assumes.

## What Loom does

- **Ingests mixed evidence at scale.** Drag in video, photo, audio, PDF, and
  document files. Loom hashes every file with SHA-256, validates by magic bytes
  (not extension), and stores the original byte-for-byte under WORM-style
  read-only semantics. Resumable uploads, batch ingest, and interrupted-job
  recovery are built in.
- **Builds a chain of custody automatically.** Every action on every asset
  (ingest, verify, rehash, proxy generation, annotation, redaction, export,
  import, relocation, deletion) is recorded in an append-only audit trail
  enforced at the database level. The trail can never be modified or back-dated,
  even by an administrator.
- **AI assists, humans decide.** Optional extras run locally: speech-to-text via
  faster-whisper, OCR via Tesseract, scene boundary detection via PySceneDetect,
  and perceptual-hash duplicate clustering. Suggestions never collapse
  ambiguity; when AI output disagrees with another asset or a human annotation,
  the contradiction is surfaced, not hidden.
- **Synthesizes timelines with explicit relationships.** Timeline events are
  synthesized objects, never raw media. Each piece of linked evidence carries an
  explicit relationship type (`supports`, `contradicts`, or `context`) so the
  timeline shows where stories agree and where they diverge. For legal work,
  uncertainty is information, not noise.
- **Exports court-ready bundles.** Each export is a signed package containing
  originals, derivatives, annotations, timeline, and the full chain of custody,
  plus a custodian certificate drafted to satisfy **FRE 902(13)/(14)**
  self-authentication and **IRE 902(11)** business-records authentication. The
  same bundle works for federal and Illinois filings. Reports are rendered as
  PDF/A-2b for archival; the manifest is JSON-LD so any conforming verifier can
  re-check the hash lineage.

## Download and install

### Desktop Lite (recommended for individuals)

Desktop Lite is a single-user, local-only build. Everything stays on your
laptop: originals, derivatives, the database, and logs. Nothing leaves the
machine unless you explicitly export a bundle.

1. Go to the project's [GitHub Releases
   page](https://github.com/jrwinget/loom/releases) and download the installer
   for your platform:
   - **Windows**: `Loom-x.y.z.msi`
   - **macOS**: `Loom-x.y.z.dmg`
   - **Linux**: `Loom-x.y.z.AppImage` or `loom_x.y.z_amd64.deb`
2. Install:
   - **Windows**: double-click the `.msi` and follow the prompts. Until the EV
     certificate is in place, Windows will warn about an unknown publisher;
     click **More info → Run anyway**.
   - **macOS**: open the `.dmg`, drag **Loom.app** to **Applications**. The
     first launch needs a right-click → **Open** to bypass Gatekeeper
     (one-time).
   - **Linux (Debian/Ubuntu)**: `sudo dpkg -i loom_*.deb`.
   - **Linux (any distro)**: `chmod +x Loom_*.AppImage` then run it from
     anywhere.
3. On first launch Loom walks you through three screens: welcome, pick a data
   directory (default `~/.loom/data`), and create your local admin account.
   That's it.

The full first-run flow, data directory layout, troubleshooting, and security
model are documented in [`docs/desktop-lite.md`](docs/desktop-lite.md).

#### Minimum requirements

- 64-bit x86-64 or arm64 CPU with AVX2 (required by some AI extras)
- 8 GB RAM (without AI extras) / 16 GB (with AI extras enabled)
- 20 GB free on the application drive, plus a data directory with at least 2×
  your expected case footage size free
- Windows 10 21H2+, macOS 11+, or Ubuntu 22.04+

For details on supported drives, NAS/SMB caveats, and why cloud sync folders
(iCloud, OneDrive, Google Drive) are refused, see the [hardware section of the
requirements doc](docs/requirements.md#hardware-targets).

### Server deploy (for organizations)

If your team needs shared cases, role-based access across multiple users, or
larger-than-laptop scale (10 TB+ per case), run the server deploy. It uses
PostgreSQL, MinIO with object lock, and Temporal for durable workflows.

Setup is technical and assumes someone comfortable with Docker. Start with
[`docs/deployment.md`](docs/deployment.md) for the local-development bring-up
and [`docs/prod-deploy.md`](docs/prod-deploy.md) for the production checklist
(TLS, backup rotation, secrets management, Temporal production config,
observability stack).

The same export bundle format flows between Desktop Lite and the server, so a
Lite case can be promoted to a server case later without reingest.

#### Prerequisites and verification

The server deploy is tested against these versions; older releases may work
but aren't validated in CI:

| Tool         | Version           | Verify with             |
| ------------ | ----------------- | ----------------------- |
| Python       | **3.12.x**        | `python --version`      |
| Node.js      | **22 LTS**        | `node --version`        |
| pnpm         | **10.x**          | `pnpm --version`        |
| Docker       | **24+**           | `docker --version`      |
| Docker Compose | **v2+**         | `docker compose version` |
| uv           | **latest**        | `uv --version`          |

Python 3.13 is **not yet validated**: a few backend dependencies (notably
`av`, `faster-whisper`) lag the Python release cycle on wheel availability,
and CI exclusively runs 3.12. If you need 3.13, expect to build wheels from
source.

#### Troubleshooting

**`compose stack refuses to start with "Set X in .env"`**
You haven't populated the mandatory credentials. Run
`cp .env.example .env`, then edit the file to override the dev sentinels
with strong values for any non-throwaway environment.

**Backend exits at startup with `secret_key is the insecure default`**
`LOOM_SECRET_KEY` is still the placeholder. Generate one and rerun:
```bash
python -c "import secrets; print(secrets.token_urlsafe(48))" >> .env
```

**Backend exits with `production credential validation failed`**
You're running with `LOOM_DEBUG=false` and `LOOM_DEPLOYMENT_PROFILE=server`,
but at least one of `LOOM_DATABASE_URL`, `LOOM_MINIO_ACCESS_KEY`, or
`LOOM_MINIO_SECRET_KEY` is still a dev sentinel. The error message lists
every offender. For local development, set `LOOM_DEBUG=true`.

**Port 8000 / 3000 / 5432 already in use**
Another process is bound to that port. On macOS/Linux:
`lsof -iTCP:8000 -sTCP:LISTEN`. Stop that process or change the port in
`.env`.

**`make migrate` fails with `connection refused`**
Postgres isn't up yet. `make up` starts the infrastructure containers;
wait for `docker compose ps` to show `postgres` as `healthy` before
running migrations.

**Docker run-time fails on Windows with "no space left on device"**
Docker Desktop ships with a small WSL2 disk allocation. Increase it via
`Settings → Resources → Advanced` and restart Docker.

For Desktop Lite-specific issues (data directory permission, port
conflict on `127.0.0.1:8000`, recovering from a force-quit during
ingest), see the
[Troubleshooting section of the Desktop Lite guide](docs/desktop-lite.md#troubleshooting).

## Security approach

Loom assumes adversarial interest in the evidence it stores. The product is
built around four non-negotiable invariants:

- **Originals are sacred.** Files land in WORM storage byte-for-byte. On Desktop
  Lite this is enforced via the OS read-only flag; on the server profile, MinIO
  object lock prevents modification or deletion. Every file is hashed with
  SHA-256 at ingest; derivatives are tracked separately and can always be
  regenerated from the original.
- **Chain of custody is append-only at the database level.** Both the ORM (every
  profile) and Postgres triggers (server profile) reject `UPDATE` and `DELETE`
  against `audit_log` and `chain_of_custody_entries`. Even direct database
  access (`psql`, restored backups, an attacker with credentials) cannot rewrite
  history.
- **No surveillance features.** Face recognition, voiceprint identification,
  suspicion scoring, and automated identity resolution are out of scope as a
  structural project decision, not a configurable toggle. Speaker diarization
  (server profile only) labels segments without persisting voiceprints. Face
  blur uses a generic detector that stores blur masks, not geometry vectors. The
  defaults are [BIPA-safe by
  construction](docs/requirements.md#privacy-and-compliance).
- **Local by default.** Desktop Lite binds the backend to `127.0.0.1` only; no
  external listener, no telemetry, no update checks. Outbound traffic happens
  only when you explicitly submit a URL for ingestion (and even then, loopback /
  private / link-local addresses are rejected).

Beyond the invariants:

- JWT auth with **argon2id** password hashing and TOTP MFA support. Access
  tokens expire in 15 min; refresh tokens are httpOnly with 7-day lifetime;
  revoked tokens are tracked.
- Server-side encryption (**SSE-S3 / AES-256**) is enforced on every MinIO
  bucket at bootstrap; SSE-KMS is supported for external KMS deployments. See
  [`docs/security/encryption.md`](docs/security/encryption.md) for algorithms,
  key storage, rotation, and what the model defends against.
- Production-profile startup **fails fast** on default credentials. The backend
  rejects the placeholder `LOOM_SECRET_KEY`, default MinIO access/secret keys,
  and the default database password; Docker Compose refuses to start when
  `MINIO_ROOT_USER`, `MINIO_ROOT_PASSWORD`, `POSTGRES_PASSWORD`, or
  `GRAFANA_ADMIN_PASSWORD` are unset.
- Three layers of authorization: **system roles** (`admin` / `analyst` /
  `viewer`), **organization roles** (`admin` / `member`), **case-level roles**
  (`owner` / `editor` / `viewer`). Every case-scoped endpoint checks case
  membership; cross-org access is impossible by construction.

The full security write-up (i.e.,threat model, auth, authorization, audit,
storage, input validation, responsible disclosure) is in
[`docs/security.md`](docs/security.md).

### Reporting vulnerabilities

Please report security issues privately by emailing the maintainers. **Do not
open a public GitHub issue.** A confirmed report receives an acknowledgement
within 72 hours and a fix target within 30 days for high-severity issues.

## How it's built

| Layer          | Technology                             |
| -------------- | -------------------------------------- |
| API            | FastAPI + Uvicorn (Python 3.12)        |
| Database       | PostgreSQL 16 (server) / SQLite (Lite) |
| Object Storage | MinIO (S3-compatible, WORM)            |
| Workflows      | Temporal (server) / in-process (Lite)  |
| Frontend       | Vite + React 18 + TypeScript           |
| UI             | shadcn/ui (Radix + Tailwind)           |
| Desktop Shell  | Tauri v2                               |
| Testing        | pytest, Vitest, Playwright             |

The repo is a monorepo with `backend/`, `frontend/`, `desktop/`, `docker/`, and
`docs/`. See [`docs/architecture.md`](docs/architecture.md) for the data model,
ingest pipeline, and workflow engine.

## Documentation

- [Architecture](docs/architecture.md): system design and the evidence spine
- [Beta requirements](docs/requirements.md): jurisdiction, hardware, dataset,
  and privacy defaults
- [Desktop Lite](docs/desktop-lite.md): install, first-run, troubleshooting
- [Deployment](docs/deployment.md): local-development bring-up
- [Production deployment](docs/prod-deploy.md): TLS, secrets, observability
- [Security](docs/security.md): auth, RBAC, audit, threat model
- [Encryption](docs/security/encryption.md): algorithms and key management
- [API reference](docs/api-reference.md): REST endpoints
- [Backup & recovery](docs/backup-recovery.md): backup procedures
- [Operational runbook](docs/runbook.md): day-to-day operations
- [AI model cards](docs/ai-model-cards.md): disclosure of every model used
- [Contributing](docs/contributing.md): development setup and PR process

## Contributing

Bug reports, feature requests, and pull requests are welcome. Read
[`docs/contributing.md`](docs/contributing.md) for code style, the test/coverage
gates, and the PR workflow.

### Reporting issues during beta

If you're a legal observer or attorney piloting Loom and you hit a workflow
problem, please open a GitHub issue with:

- **Build / version**: from the Help menu in Desktop Lite, or
  `git rev-parse HEAD` for a server install.
- **Platform**: OS + version, Loom profile (`lite` or `server`).
- **What you did, what happened, what you expected.** Steps to reproduce
  beat speculative cause-finding.
- **Logs**, if available. Desktop Lite writes to
  `~/.loom/logs/backend.log`; server installs land in their journald /
  Docker logs.
- **Sensitive evidence stays out of bug reports.** Never paste case
  metadata, file contents, or hashes that identify a real case. If a
  reproducer requires evidence-shaped data, generate a synthetic
  fixture first.

For security vulnerabilities, please email the maintainers privately
instead. See [Reporting vulnerabilities](#reporting-vulnerabilities).

## License

Loom is released under the [MIT License](LICENSE). It is built to support
civil-liberties work; please use it for that.
