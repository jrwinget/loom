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

## Commands

```bash
make up          # start docker compose services
make down        # stop services
make dev         # start all services for local development
make test        # run all tests (backend + frontend)
make lint        # run all linters
make format      # auto-format all code
make migrate     # run database migrations

# backend only
cd backend
uv run pytest tests/ -v              # run all tests
uv run pytest tests/unit/ -v         # unit tests only
uv run pytest tests/ -k test_name    # single test
uv run ruff check src tests          # lint
uv run ruff format src tests         # format
uv run mypy src                      # type check
uv run alembic upgrade head          # run migrations
uv run uvicorn loom.main:app --reload  # dev server

# frontend only
cd frontend
pnpm test                            # run tests
pnpm test -- --watch                 # watch mode
pnpm lint                            # eslint
pnpm typecheck                       # tsc --noEmit
pnpm format                          # prettier
pnpm dev                             # dev server
pnpm build                           # production build
```

## Architecture

### Monorepo Layout

- `backend/` — FastAPI + SQLAlchemy + Temporal
- `frontend/` — Vite + React 18 + TypeScript
- `docker/` — Docker Compose services
- `docs/` — project documentation

### Backend (`backend/src/loom/`)

- `main.py` — app factory with lifespan, CORS, audit middleware
- `config.py` — Pydantic BaseSettings (LOOM_ env prefix)
- `dependencies.py` — FastAPI dependency injection
- `security/` — JWT auth, RBAC, audit logging middleware
- `models/` — SQLAlchemy 2.0 models (evidence spine)
- `schemas/` — Pydantic request/response schemas
- `api/v1/` — REST endpoints (health, auth, cases, assets,
  annotations, timeline, exports)
- `services/` — business logic (case, ingest, hashing,
  storage, metadata, proxy, annotation, timeline, export)
- `workflows/` — Temporal workflow definitions
- `workers/` — Temporal worker entrypoint

### Frontend (`frontend/src/`)

- `routes/` — page components (dashboard, cases, assets,
  timeline, export)
- `components/` — layout, case, asset, timeline, annotation,
  export
- `hooks/` — TanStack Query hooks + keyboard shortcuts
- `stores/` — Zustand stores (auth, UI)
- `lib/` — API client, query keys, utilities
- `types/` — TypeScript interfaces

### Evidence Spine (Database)

users → cases → case_memberships
cases → assets → derivatives
assets → chain_of_custody_entries (append-only)
cases → annotations (typed: observation/claim/dispute/
  needs_verification/note)
cases → timeline_events → timeline_event_evidence
  (relationship: supports/contradicts/context)
cases → export_bundles
audit_log (append-only, all mutations)

### Key Design Decisions

- Timeline events are synthesized objects, never raw media.
  Evidence links have explicit relationship types to enable
  contradiction surfacing.
- Two-tier upload: ≤100MB through API, >100MB via MinIO
  presigned URL.
- File types validated by magic bytes, not extension.
- Chain of custody and audit log are append-only tables.
- Temporal workflows orchestrate the ingest pipeline:
  verify_hash → extract_metadata → generate_proxy →
  record_custody → mark_complete.

## Code Style

- **Inline comments**: lowercase
- **User-facing text / commits**: properly cased
- **Python**: 4-space indent, 80-char lines, type hints on
  all signatures, Ruff-formatted, mypy strict
- **TypeScript**: 2-space indent, 80-char lines, strict mode,
  no `any`, single quotes, trailing commas
- **Commits**: staging branch, concise messages, 2-4 bullets,
  no co-author lines
- **Tests**: 90% coverage minimum

## Security

- JWT auth with argon2 password hashing
- System roles (admin/analyst/viewer) + case roles
  (owner/editor/viewer)
- Audit middleware logs all mutations to audit_log
- Case-level authorization on every case-scoped endpoint
- Pydantic validation on all input
- Presigned URLs are time-limited (15 minutes)
