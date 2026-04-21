# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code)
when working with code in this repository.

## Project Overview

Loom is an **evidence operating system** for the National
Lawyers Guild. It combines multiple source documents (video,
photos, statements) into defensible event timelines. This is
civil-liberties tooling, not surveillance tech.

## Core Principles (Non-Negotiable)

- **Originals are sacred**: preserve original files, filenames,
  order, and hashes. WORM-style immutability via MinIO.
- **AI assists, humans decide**: AI suggests but never collapses
  ambiguity. Contradictions are surfaced, not hidden.
- **Scale on ugly reality**: resumable upload, batch ingest,
  interrupted-job recovery, proxy generation, async processing.
- **No face recognition, suspicion scoring, or automated
  identity resolution**.

## Prerequisites

- Python 3.12+
- Node.js 22+ with pnpm 10
- Docker and Docker Compose
- [uv](https://docs.astral.sh/uv/) (Python package manager)

## Setup

```bash
cp .env.example .env             # configure environment
make up                          # start infrastructure
cd backend && uv sync --all-extras && cd ..
cd frontend && pnpm install && cd ..
make migrate                     # run database migrations
make dev                         # start backend + frontend
```

API: `http://localhost:8000/docs` | Frontend: `http://localhost:3000`

## Commands

```bash
make up / make down              # docker compose lifecycle
make dev                         # start all services
make test                        # all tests (backend + frontend)
make test-backend                # backend only (with coverage)
make test-frontend               # frontend only
make lint                        # all linters + type checks
make format                      # auto-format all code
make migrate                     # alembic upgrade head
make build                       # build docker images
make deploy                      # build + start full stack
make backup / make restore       # database backup management

# backend (from backend/)
uv run pytest tests/ -v              # all tests
uv run pytest tests/unit/ -v         # unit tests only
uv run pytest tests/ -k test_name    # single test
uv run ruff check src tests          # lint
uv run ruff format src tests         # format
uv run mypy src                      # type check
uv run alembic upgrade head          # migrations
uv run uvicorn loom.main:app --reload  # dev server

# frontend (from frontend/)
pnpm test                            # vitest
pnpm test -- --watch                 # watch mode
pnpm lint                            # eslint (zero warnings)
pnpm typecheck                       # tsc --noEmit
pnpm format                          # prettier
pnpm dev                             # vite dev server
pnpm build                           # production build
```

## Architecture

### Monorepo Layout

- `backend/` — FastAPI + SQLAlchemy 2.0 + Temporal
- `frontend/` — Vite + React 18 + TypeScript + shadcn/ui
- `docker/` — Compose, nginx, postgres, temporal, prometheus,
  grafana configs
- `docs/` — architecture, security, deployment, API reference

### Backend (`backend/src/loom/`)

- `main.py` — app factory with lifespan, middleware stack
- `config.py` — Pydantic BaseSettings (`LOOM_` env prefix)
- `dependencies.py` — FastAPI dependency injection
- `security/` — auth (JWT), rbac, csrf, rate_limit, audit
  middleware (dedicated module, not inline)
- `models/` — SQLAlchemy 2.0 async models (22 tables)
- `schemas/` — Pydantic v2 request/response schemas
- `api/v1/` — REST endpoints (~25 route modules)
- `services/` — business logic (~30 service modules)
- `workflows/` — Temporal workflow + activity definitions
- `workers/` — Temporal worker entrypoint
- `templates/` — Jinja2 templates for PDF report generation
- `observability.py` — OpenTelemetry setup
- `metrics.py` — Prometheus instrumentation

### Middleware Stack (order matters)

1. Request ID (UUID per request)
2. CORS
3. Rate limiting (slowapi)
4. CSRF double-submit validation
5. Audit middleware (logs all mutations)

### Frontend (`frontend/src/`)

- `routes/` — file-based routing (cases, assets, timeline,
  export, review, settings, organizations)
- `components/` — 12 feature directories (asset, auth, case,
  export, layout, map, organization, plugin, review, timeline)
- `hooks/` — TanStack Query hooks (18 domain hooks)
- `stores/` — Zustand (auth, UI, offline-queue, toast)
- `lib/` — API client, offline client, query keys, utilities
- `types/` — TypeScript domain interfaces
- Path alias: `@` → `src` (configured in vite + tsconfig)
- Vite proxies `/api` → `http://localhost:8000`
- Tests use MSW for API mocking

### Temporal Workflows

Five async workflow pipelines, each with a workflow +
activities module:

- **ingest**: verify_hash → extract_metadata → generate_proxy
  → record_custody → mark_complete
- **export**: bundle assets + annotations into verified package
- **transcription**: speech-to-text via faster-whisper
- **ocr**: text extraction via pytesseract
- **scene_detection**: shot boundary detection via scenedetect

### Evidence Spine (Database)

```
users → cases → case_memberships
cases → assets → derivatives
assets → chain_of_custody_entries (append-only)
cases → annotations (observation/claim/dispute/
  needs_verification/note)
cases → timeline_events → timeline_event_evidence
  (supports/contradicts/context)
cases → export_bundles
assets → transcript_segments, ocr_regions, scenes
assets → redactions (blur/pixelate/mute derivatives)
cases → duplicate_clusters → duplicate_cluster_members
users → revoked_tokens (JWT invalidation)
audit_log (append-only, all mutations)
```

### Key Design Decisions

- Timeline events are synthesized objects, never raw media.
  Evidence links carry explicit relationship types to surface
  contradictions.
- Two-tier upload: ≤100MB through API, >100MB via MinIO
  presigned URL (15-minute expiry).
- File types validated by magic bytes, not extension.
- Chain of custody and audit_log are append-only (no UPDATE
  or DELETE).
- AI dependencies (faster-whisper, pyannote, pytesseract,
  scenedetect) are optional extras — services degrade
  gracefully when not installed. Install with:
  `uv sync --extra ai --extra provenance`
- Full-text search uses ILIKE across transcripts, OCR,
  annotations, events, and asset filenames.
- Duplicate detection uses perceptual hashing (average hash)
  with hamming distance clustering.
- Secret key validated at startup: must be ≥32 chars, rejects
  the default `change-me-in-production` value.

### Configuration

All env vars use the `LOOM_` prefix (e.g., `LOOM_SECRET_KEY`,
`LOOM_DATABASE_URL`). See `backend/src/loom/config.py` for
all settings and defaults. Key groups:

- Database: `database_url`, `db_pool_size`, `db_pool_timeout`
- Storage: `minio_endpoint`, `minio_access_key`, `minio_secure`
- Auth: `secret_key`, `access_token_expire_minutes` (15),
  `refresh_token_expire_days` (7)
- CORS: `cors_origins` (list of allowed origins, defaults to
  `["http://localhost:3000"]`)
- Observability: `otel_enabled`, `otel_service_name`

### Migrations

Alembic migrations in `backend/alembic/versions/` use
sequential numbering: `NNN_description.py` (e.g.,
`001_initial_schema.py`). Current head: `003`. CI runs a
full round-trip test: upgrade head → downgrade base →
upgrade head.

## CI Pipeline

Runs on pushes/PRs to `staging` and `main`:

1. Lint backend (ruff + mypy) and frontend (eslint + prettier
   + tsc) in parallel
2. Test backend (pytest, 90% coverage gate) and frontend
   (vitest) in parallel
3. Migration round-trip test against real PostgreSQL
4. Security scan (pip-audit, pnpm audit, Trivy on Docker
   images)
5. Docker build + smoke test (verify containers start and
   serve traffic)

## Code Style

- **Inline comments**: lowercase
- **User-facing text / commits**: properly cased
- **Python**: 4-space indent, 80-char lines, type hints on
  all signatures, Ruff-formatted, mypy strict
- **TypeScript**: 2-space indent, 80-char lines, strict mode,
  no `any`, single quotes, trailing commas
- **Commits**: staging branch, concise messages, 2-4 bullets,
  no co-author lines
- **Tests**: 90% coverage minimum (both backend and frontend)

## Security

- JWT auth with argon2 password hashing, MFA support
- System roles (admin/analyst/viewer) + case roles
  (owner/editor/viewer)
- Dedicated `security/` module: auth, RBAC, CSRF
  double-submit, rate limiting (slowapi), audit middleware
- Case-level authorization on every case-scoped endpoint
- Pydantic validation on all input
- Presigned URLs are time-limited (15 minutes)
- Secret key validation enforced at startup
