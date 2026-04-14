# Security

## Threat Model

Loom assumes adversarial interest in the evidence it stores.
Threat actors may include parties who want to:
- Access evidence they are not authorized to view
- Modify or delete evidence to suppress it
- Discredit evidence by breaking chain of custody
- Identify sources or witnesses from metadata

## Authentication

- Passwords hashed with argon2id (memory-hard)
- JWT access tokens with 15-minute expiry
- Refresh tokens with 7-day expiry in httpOnly cookies
- MFA support designed in (TOTP column on user model)

## Authorization

- System roles: admin, analyst, viewer
- Case-level roles: owner, editor, viewer
- Every case-scoped endpoint checks membership
- Permission matrix:
  - Upload: case editor+
  - Annotate: case editor+
  - Export: case editor+
  - View: case viewer+
  - Manage users: system admin
  - Delete: system admin + case owner

## Audit Trail

- All mutations logged to append-only audit_log table
- Chain of custody entries for every asset action
- Audit records include: actor, action, resource, IP,
  user agent, timestamp
- Cannot be modified or deleted (database constraints)

## Storage Security

- Originals in WORM-enabled MinIO bucket (object lock)
- Presigned URLs are time-limited (15 minutes)
- No direct public access to storage buckets
- File uploads validated by magic bytes, not extension
- Cryptographic hashes (SHA-256 + SHA-512) on all files

## Input Validation

- All API input validated by Pydantic schemas
- No raw user input reaches SQL or storage
- File type allow-list (not block-list)
- X-Request-Id on every response for traceability

## Responsible Disclosure

If you discover a security vulnerability, please report it
privately by emailing the maintainers. Do not open a public
issue for security vulnerabilities.
