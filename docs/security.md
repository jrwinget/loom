# Security

This doc covers Loom's threat model, authentication and
authorization, audit trail, storage protections, input
validation, and the responsible-disclosure process.

For algorithms, key storage, and rotation see
[`security/encryption.md`](security/encryption.md). For the
jurisdictional privacy posture (BIPA, Illinois Eavesdropping
Act, FOIA) see the
[Privacy and compliance section of the requirements doc](requirements.md#privacy-and-compliance).

## Threat model

Loom assumes adversarial interest in the evidence it stores.
In-scope adversaries include parties who want to:

- Read evidence they are not authorized to view.
- Modify or delete evidence to suppress it.
- Discredit evidence by breaking the chain of custody.
- Identify sources, witnesses, or counsel from metadata.

Out of scope: nation-state offensive capabilities against
hardware, supply-chain attacks against the upstream
toolchain, and physical seizure of the device. Loom hardens
the application layer; physical and operational security are
the operator's responsibility.

## Authentication

- Passwords hashed with **argon2id** (memory-hard).
- JWT access tokens with a 15-minute expiry; refresh tokens
  in httpOnly cookies with a 7-day lifetime.
- TOTP MFA support (column on the user model; enrolment flow
  in the frontend).
- Revoked tokens tracked in `revoked_tokens` and checked on
  refresh, so logout actually invalidates the session even
  before the access token expires.

## Authorization

Three layers, all enforced at the dependency-injection layer:

- **System roles**: `admin`, `analyst`, `viewer`.
- **Organization roles**: `admin`, `member`.
- **Case-level roles**: `owner`, `editor`, `viewer`, joined
  to users via `case_memberships`.

Every case-scoped endpoint checks case membership; every
organization-scoped endpoint checks org membership.
Cross-organization access without an explicit shared-evidence
link is impossible by construction.

Permission summary:

| Action          | Required role                          |
| --------------- | -------------------------------------- |
| Upload          | case editor or owner                   |
| Annotate        | case editor or owner                   |
| Export          | case editor or owner                   |
| View            | case viewer or higher                  |
| Manage users    | system admin                           |
| Delete asset    | system admin or case owner             |
| Purge case      | case owner (typed confirmation + log)  |

## Audit trail and chain of custody

`audit_log` records every mutation: actor, action, resource
type/id, IP, user agent, request id, timestamp.
`chain_of_custody_entries` records every action on every
asset (ingest, verify, rehash, proxy generation, annotation,
redaction, export, import, relocation, deletion).

**Both tables are append-only at the database level**, not
just by convention:

- The ORM registers `before_update` / `before_delete` event
  listeners that raise `AppendOnlyViolationError`. This
  applies to every profile, including SQLite-backed Desktop
  Lite.
- On the server profile, migration 011 installs Postgres
  triggers that produce the same rejection from raw SQL —
  `psql`, restored backups, or any caller that bypasses the
  ORM.

Chain-of-custody entries include SHA-256 before/after where
relevant and a signed statement (HMAC with the install's
storage signing secret). This lineage is exported with every
court bundle as both line-per-event CSV (paralegal-readable)
and JSON-LD (machine-verifiable).

## Storage security

- Originals live in `loom-originals`, a WORM-enabled MinIO
  bucket with object lock. Object lock prevents modification
  or deletion regardless of credentials.
- Server-side encryption (**SSE-S3 / AES-256**) is set on
  every bucket — originals, derivatives, backups — at MinIO
  bootstrap. SSE-KMS is supported for external KMS
  deployments; see
  [encryption.md](security/encryption.md).
- Presigned URLs are time-limited (15 minutes).
- File uploads are validated by **magic bytes**, not
  extension, against an allow-list.
- No public bucket access; all reads go through presigned
  URLs with auditable issuance.
- Two-tier upload: ≤100 MB through the API; >100 MB via a
  presigned URL straight to MinIO, then a `/complete` call to
  finalize hash and custody.

On Desktop Lite, "WORM" is enforced via the OS read-only flag
applied immediately after each write into
`<data_dir>/buckets/loom-originals/`. The ingest pipeline
re-verifies the read-only bit after every write; NAS / SMB /
NFS mounts that silently drop the flag are flagged at first
run.

Cloud-sync directories (iCloud, OneDrive, Google Drive) are
**rejected** as data directories — they rewrite files during
sync, which breaks hash integrity.

## Production credential enforcement

The backend refuses to start in non-debug, server-profile
mode when default dev credentials are in use:

- `LOOM_SECRET_KEY` cannot be the placeholder
  `change-me-in-production`, must be ≥32 characters.
- `LOOM_DATABASE_URL` cannot include the dev sentinel
  `loom:loom_dev@`.
- `LOOM_MINIO_ACCESS_KEY` cannot be `loom_minio`;
  `LOOM_MINIO_SECRET_KEY` cannot be `loom_minio_dev`.

A startup that fails any of these checks raises
`ValueError` and aborts before opening any port.

Docker Compose enforces a parallel set at the orchestration
layer: `POSTGRES_PASSWORD`, `MINIO_ROOT_USER`,
`MINIO_ROOT_PASSWORD`, and `GRAFANA_ADMIN_PASSWORD` use the
mandatory-env-var pattern (`${VAR:?Set VAR in .env}`). A
missing value fails the stack instead of silently
substituting a known default.

## Input validation

- All API input passes through Pydantic v2 schemas with
  strict types.
- File-type validation is allow-list by magic bytes.
- CORS is restricted to `LOOM_CORS_ORIGINS` (must be an
  explicit list; `*` is rejected; each entry must be an
  absolute http(s) origin with no path).
- CSRF protection via double-submit cookie + header on every
  mutation.
- Rate limiting via `slowapi` (per-IP).
- A `X-Request-Id` header is set on every response for
  traceability.

## Network posture

- **Server profile**: production deploys terminate TLS at
  nginx (TLS 1.3 only since #71). Internal services are not
  exposed publicly; MinIO and Postgres bind to private
  interfaces.
- **Desktop Lite**: backend binds to `127.0.0.1` only. There
  is no listener on any external interface. No telemetry, no
  update checks, no crash reporting. The single source of
  outbound traffic is URL ingestion (when the user explicitly
  submits a URL), and even there a SSRF dispatcher rejects
  loopback / private / link-local destinations.

## Bundle signing

Court-export bundles include a SHA-256 of every asset and a
SHA-256 of the canonical JSON manifest. The manifest hash is
the single value the case owner attests to on the printed
custodian certificate. Optional **Ed25519 detached
signatures** can be enabled by setting
`LOOM_BUNDLE_SIGNING_KEY` to a PEM-encoded private key; leave
it unset to skip signing.

Trusted timestamping (RFC 3161) and blockchain anchoring are
deferred — see the
[Deferred section of the requirements doc](requirements.md#deferred--out-of-scope-for-beta).

## Responsible disclosure

If you discover a security vulnerability, please report it
privately by emailing the maintainers. **Do not open a
public GitHub issue.**

You will get an acknowledgement within 72 hours and a fix
target within 30 days for high-severity issues. Coordinated
disclosure is welcome; please give us a chance to land a
patch before publishing details.
