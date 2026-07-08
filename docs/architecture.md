# Architecture

## System overview

Loom is a monorepo with three application surfaces and a
shared infrastructure layer:

1. **FastAPI backend** — REST API, business logic, persistence.
2. **Temporal workers** — durable workflow pipelines for
   ingest, export, transcription, OCR, and scene detection.
3. **React + Tauri frontend** — web app for the server
   profile, Tauri shell for Desktop Lite.

Two deployment profiles share the same code:

- **Server profile**: Postgres, MinIO with object lock,
  Temporal cluster, multi-user. Used by organizations.
- **Desktop Lite**: SQLite, local filesystem with OS
  read-only flag for WORM, in-process worker, single user.
  Used by individual practitioners; ships as a Tauri
  installer.

The data model, business logic, audit trail, and export
format are identical across profiles — a Lite case can be
exported and imported into the server profile (and vice
versa) without re-ingesting evidence.

## Data flow

### Ingest pipeline

```
Upload → Validate (magic bytes) → Hash (SHA-256)
→ Store in MinIO (WORM) → Record chain of custody
→ Start Temporal workflow:
    1. Verify hash integrity
    2. Extract metadata (PyAV + ExifTool)
    3. Generate proxies (720p video, thumbnails, waveform)
    4. Record derivative custody
    5. Mark asset complete
```

Files ≤100 MB are uploaded through the API. Files >100 MB
get a presigned URL good for 15 minutes and upload directly
to MinIO; the client then calls `/complete` to trigger
hashing and the custody record.

### Evidence model

The evidence spine ensures every claim traces to source
material:

- **Assets**: immutable originals stored with a SHA-256 hash
  at ingest. Originals are never converted; the court
  receives the byte-exact original plus its hash.
- **Derivatives**: regenerable review artifacts (proxies,
  thumbnails, transcripts, OCR regions, redactions). They
  carry their own hashes but can be rebuilt from the
  original at any time.
- **Annotations**: human observations with explicit types
  (`observation`, `claim`, `dispute`, `needs_verification`,
  `note`).
- **Timeline events**: synthesized objects, never raw media.
  Each links to source assets with an explicit relationship
  type — `supports`, `contradicts`, or `context`.
- **Chain of custody** and **audit log**: append-only at the
  database level. Every action is logged; nothing can be
  modified or deleted, even by a system admin.
- **Redactions**: track blur / pixelate / mute operations on
  derivatives. Originals are never modified.
- **Revoked tokens**: invalidated JWTs; checked on every
  refresh.

### Contradiction surfacing

When the evidence linked to a timeline event includes both
`supports` and `contradicts` relationships, the event is
flagged. Loom does not collapse the disagreement into a
single "best guess." For legal work, uncertainty is
information.

### Duplicate detection

Perceptual hashing (average hash) plus hamming-distance
clustering groups visually similar assets without merging
them. The clusters surface in the UI for analyst review;
Loom never auto-deletes duplicates.

### Correlation

A correlation service identifies likely multi-perspective
groupings (e.g., the same incident captured by two cameras)
using time, location, and content signals. Confidence and
proposed time offsets are returned per pair; analysts
validate or reject groupings in the UI (the validator panel
is tracked in #41).

## Authentication and authorization

- JWT access tokens (15-minute expiry) signed with the
  install's `LOOM_SECRET_KEY`; passwords hashed with
  argon2id; TOTP MFA supported.
- System roles (`admin`, `analyst`, `viewer`), org roles
  (`admin`, `member`), case roles (`owner`, `editor`,
  `viewer`).
- Frontend routes wrap in `ProtectedRoute` and redirect
  unauthenticated traffic to `/login`.
- Audit middleware logs every mutation to the append-only
  `audit_log` table; CSRF middleware validates a
  double-submit cookie + header on every mutation.

See [`security.md`](security.md) for the full posture.

## Storage

Server profile:

- **`loom-originals`**: WORM-enabled MinIO bucket with
  object lock. Originals are encrypted at rest with
  SSE-S3 / AES-256 (SSE-KMS supported for external KMS).
- **`loom-derivatives`**: standard MinIO bucket; same
  encryption, no object lock since derivatives are
  regenerable.
- **`loom-backups`**: scheduled Postgres dumps + MinIO
  snapshots for disaster recovery.

Desktop Lite:

- All assets live under `<data_dir>/buckets/`; originals
  get the OS read-only flag immediately after write. The
  ingest pipeline re-verifies the flag after every write,
  surfacing a warning if the filesystem silently dropped
  it (some NAS / SMB mounts do this).

## Workflow engine

Temporal provides durable execution for long-running
pipelines. If a step fails (e.g., a GPU timeout during
proxy generation), Temporal retries with configurable
policies. Failed workflows stay in failed state for human
review — originals are never lost.

On Desktop Lite, the same activity functions run in-process
behind a thin Temporal-shaped facade so the rest of the code
doesn't branch on profile. There is no Temporal server
running on Lite installs. Every endpoint dispatches through a
single gateway (`loom.workflows.dispatch.dispatch_workflow`):
on the server profile it starts a Temporal workflow; on Lite it
runs the workflow's activity sequence as a background task. The
activity order and retry policy for both paths live in one place
(`loom.workflows.sequences`), so they cannot drift. Workflow
status on Lite is reported from in-process state, falling back to
the persisted rows the workflow produced. Activities whose
optional AI dependencies (OCR, transcription, scene detection)
are not bundled with the desktop build degrade gracefully to
empty results rather than failing.

## Cognitive engineering (UI)

The frontend applies a few load-bearing principles:

- Always show current position (timestamp, frame, asset).
- Force explicit uncertainty: `time_precision` and
  `location_confidence` are required fields on annotations
  and events.
- Surface contradictions visually rather than hiding them.
- Keyboard-first review workflow for speed.
- Color-coded annotation types for rapid scanning.

## Database migrations

Migrations live in `backend/alembic/versions/` with
sequential numbering (`NNN_description.py`). The current head
is in step with the model file; CI runs a full round-trip
test on real Postgres (upgrade head → downgrade base →
upgrade head) on every PR.

Notable migrations:

- `001_initial_schema` — base evidence spine.
- `010_add_url_ingest_provenance` — URL ingestion provenance.
- `011_append_only_triggers` — Postgres triggers enforcing
  append-only semantics on `audit_log` and
  `chain_of_custody_entries`.

## Code layout

```
loom/
├── backend/              FastAPI + SQLAlchemy 2.0 + Temporal
│   ├── src/loom/
│   │   ├── api/v1/       REST endpoints
│   │   ├── models/       SQLAlchemy 2.0 async models
│   │   ├── schemas/      Pydantic v2 request/response
│   │   ├── services/     business logic
│   │   ├── workflows/    Temporal workflow + activities
│   │   ├── workers/      worker entry-points
│   │   ├── security/     auth, RBAC, CSRF, rate limit, audit
│   │   ├── templates/    Jinja2 templates for PDF reports
│   │   ├── observability.py  OpenTelemetry setup
│   │   └── metrics.py    Prometheus instrumentation
│   ├── tests/            pytest suite
│   └── alembic/          database migrations
├── frontend/             Vite + React 18 + TypeScript
├── desktop/              Tauri v2 shell for Desktop Lite
├── docker/               compose, nginx, prometheus, grafana
└── docs/                 architecture, security, deployment, …
```
