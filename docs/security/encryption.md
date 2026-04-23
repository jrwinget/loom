# Encryption

This document states Loom's encryption posture concretely —
algorithms, key management, rotation, and what the system does
and does not defend against. Written for operators, auditors,
and clients who need to answer "is our evidence encrypted?"
with a citation, not a hand-wave.

## At rest

### Object storage (MinIO / S3)

Every object in the `loom-originals`, `loom-derivatives`, and
`loom-backups` buckets is encrypted with **SSE-S3 (AES-256-GCM)**.
The `minio-setup` service in `docker/docker-compose.yml` applies
`mc encrypt set sse-s3` to each bucket on first boot; re-running
`docker compose up` is idempotent.

Encryption is server-side: the MinIO server receives the plaintext
over the internal network, encrypts it with a per-object data key,
and stores only the ciphertext. The data key is wrapped by a master
key managed by MinIO. For self-hosted deployments this master key
lives on the MinIO host's disk (`.minio.sys/config/config.kv`),
which is why the host filesystem should be on an encrypted volume
(LUKS on Linux, FileVault on macOS). For the reference deployment
we assume the operator has provisioned such a volume.

### Database (Postgres)

Loom does not perform column-level encryption inside Postgres.
The evidence spine (`audit_log`, `chain_of_custody_entries`,
timelines) contains no keying material — the sensitive payloads
live in object storage. Operators who need database-at-rest
encryption beyond filesystem encryption should enable Postgres
TDE via their cloud provider or deploy a block-level encrypted
volume (LUKS / AWS EBS default encryption / equivalent).

The `audit_log` and `chain_of_custody_entries` tables are
**append-only**; ORM-level event listeners and Postgres triggers
reject UPDATE and DELETE so a DB-level attacker cannot silently
rewrite the tamper-evident record. See `loom.models._append_only`
and migration `011_append_only_triggers.py`.

### Backup encryption

`make backup` pipes the database dump through `gpg --encrypt
--recipient $BACKUP_GPG_RECIPIENT` when the variable is set in
`.env`. Leaving it unset produces an **unencrypted** dump, which
is convenient in development but wrong for production — CI flags
production deploys that leave it blank. See
`docs/backup-recovery.md`.

### Desktop Lite

Desktop Lite stores originals on the local filesystem with WORM
read-only semantics. It relies on the host's disk encryption
(FileVault on macOS, BitLocker on Windows, LUKS on Linux) for
at-rest protection — there is no additional layer. The
SQLite database lives under the same directory and inherits the
same protection. See `docs/desktop-lite.md` for the full data
layout.

## In transit

### External (browser ↔ nginx)

Production deployments terminate TLS at nginx
(`docker/nginx/nginx-tls.conf`). The server listens on **TLS 1.3
only** with:

- Strict-Transport-Security: 2 years, `includeSubDomains; preload`
- `ssl_session_tickets off`
- Cipher suite negotiated by TLS 1.3 (no manual list)

All browsers shipped since late 2019 support TLS 1.3 (Chrome 70+,
Firefox 63+, Safari 14+, Edge 79+). Clients without TLS 1.3 will
fail the handshake — this is intentional. If a beta deployment
has a documented need for TLS 1.2 (a locked-down client on a
legacy OS), add `TLSv1.2` back to `ssl_protocols` in the deploy's
nginx config override, not in the default.

### Internal (services inside the compose network)

Services on the internal Docker network speak plaintext HTTP /
Postgres wire protocol to each other. The threat model assumes
the Docker network is private; if you're running across
untrusted hosts (multi-node Swarm, unmanaged Kubernetes), enable
mTLS on the service mesh layer (Linkerd, Istio, or a cloud-
provider equivalent). This is not something Loom's default
compose stack provides.

### Presigned URLs

MinIO presigned URLs for originals + derivatives are signed with
HMAC-SHA256 and expire after 15 minutes. They convey **read
authorization**, not encryption — the underlying transport is
still TLS. On Desktop Lite the loopback signer uses a per-install
`LOOM_STORAGE_SIGNING_SECRET` provisioned on first run via
`tauri-plugin-store`.

## Key management

### Server profile

| Key                              | Where it lives                                          | Rotation                     |
| -------------------------------- | ------------------------------------------------------- | ---------------------------- |
| MinIO root password              | `.env` / secret store                                   | On incident; no forced sched |
| MinIO SSE master key             | MinIO host disk (encrypted volume)                      | Requires bucket rotation     |
| Postgres password                | `.env` / secret store                                   | On incident                  |
| `LOOM_SECRET_KEY` (JWT)          | `.env` / secret store; ≥32 chars; validated at startup  | Rotate quarterly             |
| GPG backup recipient key         | Operator-managed                                        | Operator policy              |
| TLS certificate + key            | `./docker/nginx/certs/fullchain.pem`, `privkey.pem`     | Per issuer (90 days on ACME) |

### SSE-KMS (optional)

For deployments with an external KMS (AWS KMS, HashiCorp Vault,
GCP KMS), run MinIO with KES. Set:

```
MINIO_KMS_KES_ENDPOINT=https://kes:7373
MINIO_KMS_KES_KEY_NAME=loom-evidence-key
MINIO_KMS_KES_CERT_FILE=/etc/kes/client.crt
MINIO_KMS_KES_KEY_FILE=/etc/kes/client.key
```

in the `minio` service, then change the `minio-setup` commands
from `mc encrypt set sse-s3` to `mc encrypt set sse-kms
loom-evidence-key`. The rest of Loom is unaffected — the change
is transparent at the application layer.

### Desktop Lite

| Key                                | Where it lives                                    |
| ---------------------------------- | ------------------------------------------------- |
| Host disk encryption key           | OS-managed (FileVault / BitLocker / LUKS)         |
| `LOOM_STORAGE_SIGNING_SECRET`      | `tauri-plugin-store` (per-install random)         |
| `LOOM_SECRET_KEY` (JWT)            | `tauri-plugin-store` (per-install random)         |

## What we defend against

- An attacker with stolen object-store ciphertext (backup tape
  loss, cloud-bucket misconfig): cannot read evidence without the
  master key.
- An attacker with a captured TLS session (on-path observer):
  cannot decrypt in real time or later, given TLS 1.3 forward
  secrecy.
- A database-layer attacker: cannot silently mutate
  `audit_log` or `chain_of_custody_entries` (rejected by trigger).
- A lost laptop running Desktop Lite: the disk is worthless
  without the OS login credential, assuming FileVault/BitLocker/
  LUKS is enabled.

## What we do not defend against

- A **root-compromised host**. An attacker with shell on the
  MinIO host can read the master key from disk and decrypt the
  bucket. Use an external KMS if this threat is in scope.
- An attacker who **steals the `LOOM_SECRET_KEY`**: can forge
  valid JWTs until the key is rotated. Rotate on any suspected
  compromise.
- **Coercion** (legal orders, physical threat): encryption does
  not prevent disclosure under a subpoena. Chain-of-custody and
  audit logs will still record the access.
- **Memory-forensic attacks** on a running host: objects are
  plaintext in server RAM while being served.

## Acceptance check

After bringing up the stack:

```bash
mc alias set loom http://localhost:9000 loom_minio loom_minio_dev
mc encrypt info loom/loom-originals
mc encrypt info loom/loom-derivatives
mc encrypt info loom/loom-backups
```

Each command should report `Auto encryption 'sse-s3' is enabled`.

Upload a test object and confirm it carries the
`X-Amz-Server-Side-Encryption: AES256` response header:

```bash
mc cp README.md loom/loom-originals/smoke.txt
mc stat loom/loom-originals/smoke.txt | grep -i encryption
# Expected: Encryption: aws:kms/... (sse-kms) OR encryption: AES256 (sse-s3)
```

## References

- [MinIO object encryption](https://min.io/docs/minio/linux/administration/server-side-encryption.html)
- [MinIO KES + external KMS](https://min.io/docs/kes/)
- [NIST SP 800-175B — Key Management](https://csrc.nist.gov/publications/detail/sp/800-175b/rev-1/final)
- Loom security overview: [docs/security.md](../security.md)
- Loom backup posture: [docs/backup-recovery.md](../backup-recovery.md)
