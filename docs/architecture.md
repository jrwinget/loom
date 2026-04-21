# Architecture

## System Overview

Loom is a monorepo with three main components:

1. **FastAPI backend** — REST API, business logic, database
2. **Temporal workers** — durable workflow pipelines for
   ingest and export
3. **React frontend** — evidence review workspace

## Data Flow

### Ingest Pipeline

```
Upload → Validate (magic bytes) → Hash (SHA-256 + SHA-512)
→ Store in MinIO (WORM) → Record chain of custody
→ Start Temporal workflow:
  1. Verify hash integrity
  2. Extract metadata (PyAV + ExifTool)
  3. Generate proxies (720p video, thumbnails, waveform)
  4. Record derivative custody
  5. Mark asset complete
```

### Evidence Model

The evidence spine ensures traceability:

- **Assets** are immutable originals stored with
  cryptographic hashes
- **Derivatives** are generated review artifacts (proxies,
  thumbnails, transcripts)
- **Annotations** are human observations with explicit types
  (observation, claim, dispute, needs_verification, note)
- **Timeline events** are synthesized objects that reference
  source evidence with explicit relationship types
  (supports, contradicts, context)
- **Chain of custody** is an append-only log of every action
  on an asset
- **Redactions** track blur/pixelate/mute operations applied
  to derivatives (originals are never modified)
- **Revoked tokens** track invalidated JWTs for secure logout

### Contradiction Surfacing

When evidence linked to a timeline event includes both
"supports" and "contradicts" relationships, the system flags
the event. This prevents the tool from hiding ambiguity —
for legal work, uncertainty is information.

## Authentication and Authorization

- JWT access tokens (15-minute expiry) with argon2 hashing
- Token revocation via `revoked_tokens` table (checked on
  refresh)
- System roles: admin, analyst, viewer
- Case-level roles: owner, editor, viewer
- Frontend routes protected by `ProtectedRoute` wrapper
  (redirects to `/login` when unauthenticated)
- Audit middleware logs all mutations to an append-only
  audit_log table

## Storage

- **loom-originals**: WORM-enabled MinIO bucket for original
  evidence files. Object lock prevents modification or
  deletion.
- **loom-derivatives**: Standard MinIO bucket for generated
  artifacts. Can be regenerated from originals.

## Two-Tier Upload

- Files ≤100MB: uploaded through the API (multipart)
- Files >100MB: client gets a presigned URL and uploads
  directly to MinIO, then calls /complete to finalize

## Workflow Engine

Temporal provides durable execution for long-running
pipelines. If a step fails (e.g., GPU timeout during proxy
generation), Temporal retries with configurable policies.
Failed workflows stay in failed state for human review —
originals are never lost.

## Cognitive Engineering (UI)

The frontend applies cognitive engineering principles:
- Always show current position (timestamp, frame number)
- Force explicit uncertainty (time_precision,
  location_confidence are required fields)
- Surface contradictions visually rather than hiding them
- Keyboard-first review workflow for speed
- Color-coded annotation types for rapid scanning
