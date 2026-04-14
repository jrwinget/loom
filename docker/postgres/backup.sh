#!/usr/bin/env bash
set -euo pipefail

# loom postgres backup script
# uses pg_dump custom format, uploads to minio, manages retention
# supports optional gpg encryption via BACKUP_GPG_RECIPIENT

BACKUP_DIR="${BACKUP_DIR:-/backups}"
TIMESTAMP="$(date -u +%Y-%m-%dT%H-%M-%S)"
BACKUP_FILE="loom-${TIMESTAMP}.dump.gz"
BACKUP_PATH="${BACKUP_DIR}/${BACKUP_FILE}"

PGHOST="${PGHOST:-postgres}"
PGPORT="${PGPORT:-5432}"
PGUSER="${POSTGRES_USER:-loom}"
PGDATABASE="${POSTGRES_DB:-loom}"
export PGPASSWORD="${POSTGRES_PASSWORD:-loom_dev}"

MINIO_ALIAS="${MINIO_ALIAS:-loom}"
MINIO_ENDPOINT="${MINIO_ENDPOINT:-http://minio:9000}"
MINIO_BUCKET="${MINIO_BACKUP_BUCKET:-loom-backups}"
MINIO_ACCESS_KEY="${MINIO_ROOT_USER:-loom_minio}"
MINIO_SECRET_KEY="${MINIO_ROOT_PASSWORD:-loom_minio_dev}"

LOCAL_RETENTION_DAYS="${LOCAL_RETENTION_DAYS:-7}"
REMOTE_RETENTION_DAYS="${REMOTE_RETENTION_DAYS:-30}"

GPG_RECIPIENT="${BACKUP_GPG_RECIPIENT:-}"
UPLOAD_MAX_ATTEMPTS=3

LOG_PREFIX="[loom-backup]"

log() { echo "${LOG_PREFIX} $(date -u +%Y-%m-%dT%H:%M:%SZ) $*"; }
log_error() { echo "${LOG_PREFIX} $(date -u +%Y-%m-%dT%H:%M:%SZ) ERROR: $*" >&2; }

cleanup() {
    unset PGPASSWORD
}
trap cleanup EXIT

# ensure backup directory exists
mkdir -p "${BACKUP_DIR}"

# ── pre-flight: verify postgres is accepting connections ────
log "checking postgres readiness"
MAX_READY_ATTEMPTS=5
for i in $(seq 1 ${MAX_READY_ATTEMPTS}); do
    if pg_isready -h "${PGHOST}" -p "${PGPORT}" -U "${PGUSER}" -q; then
        log "postgres is ready"
        break
    fi
    if [ "${i}" -eq "${MAX_READY_ATTEMPTS}" ]; then
        log_error "postgres not ready after ${MAX_READY_ATTEMPTS} attempts"
        exit 1
    fi
    log "postgres not ready, retrying in ${i}s..."
    sleep "${i}"
done

# ── pg_dump ─────────────────────────────────────────────────
log "starting backup of database '${PGDATABASE}' on ${PGHOST}:${PGPORT}"

if pg_dump \
    -h "${PGHOST}" \
    -p "${PGPORT}" \
    -U "${PGUSER}" \
    -d "${PGDATABASE}" \
    -Fc \
    --no-owner \
    --no-acl \
    | gzip > "${BACKUP_PATH}"; then
    BACKUP_SIZE=$(stat -c%s "${BACKUP_PATH}" 2>/dev/null || stat -f%z "${BACKUP_PATH}" 2>/dev/null || echo "unknown")
    log "dump complete: ${BACKUP_FILE} (${BACKUP_SIZE} bytes)"
else
    log_error "pg_dump failed"
    rm -f "${BACKUP_PATH}"
    exit 1
fi

# ── integrity verification ──────────────────────────────────
log "verifying backup integrity"
if ! gunzip -t "${BACKUP_PATH}" 2>/dev/null; then
    log_error "backup integrity check failed — gzip corrupted"
    rm -f "${BACKUP_PATH}"
    exit 1
fi
log "integrity check passed"

# ── optional gpg encryption ─────────────────────────────────
if [ -n "${GPG_RECIPIENT}" ]; then
    log "encrypting backup with gpg (recipient: ${GPG_RECIPIENT})"
    if gpg --batch --yes --trust-model always \
        -r "${GPG_RECIPIENT}" \
        -o "${BACKUP_PATH}.gpg" \
        -e "${BACKUP_PATH}"; then
        rm -f "${BACKUP_PATH}"
        BACKUP_PATH="${BACKUP_PATH}.gpg"
        BACKUP_FILE="${BACKUP_FILE}.gpg"
        log "encryption complete"
    else
        log_error "gpg encryption failed"
        exit 1
    fi
fi

# ── upload to minio with retry ──────────────────────────────
log "configuring minio client"
mc alias set "${MINIO_ALIAS}" "${MINIO_ENDPOINT}" "${MINIO_ACCESS_KEY}" "${MINIO_SECRET_KEY}" --api S3v4 2>/dev/null

log "ensuring bucket '${MINIO_BUCKET}' exists"
mc mb --ignore-existing "${MINIO_ALIAS}/${MINIO_BUCKET}"

UPLOAD_SUCCESS=false
for attempt in $(seq 1 ${UPLOAD_MAX_ATTEMPTS}); do
    log "uploading ${BACKUP_FILE} to minio (attempt ${attempt}/${UPLOAD_MAX_ATTEMPTS})"
    if mc cp "${BACKUP_PATH}" "${MINIO_ALIAS}/${MINIO_BUCKET}/${BACKUP_FILE}"; then
        log "upload complete"
        UPLOAD_SUCCESS=true
        break
    fi
    if [ "${attempt}" -lt "${UPLOAD_MAX_ATTEMPTS}" ]; then
        BACKOFF=$((attempt * 5))
        log "upload failed, retrying in ${BACKOFF}s..."
        sleep "${BACKOFF}"
    fi
done

if [ "${UPLOAD_SUCCESS}" != true ]; then
    log_error "minio upload failed after ${UPLOAD_MAX_ATTEMPTS} attempts — local backup retained at ${BACKUP_PATH}"
    exit 1
fi

# ── local retention ─────────────────────────────────────────
log "pruning local backups older than ${LOCAL_RETENTION_DAYS} days"
find "${BACKUP_DIR}" -name "loom-*.dump.gz*" -type f -mtime +"${LOCAL_RETENTION_DAYS}" -delete 2>/dev/null || true
LOCAL_COUNT=$(find "${BACKUP_DIR}" -name "loom-*.dump.gz*" -type f | wc -l)
log "local backups remaining: ${LOCAL_COUNT}"

# ── remote retention ────────────────────────────────────────
log "pruning remote backups older than ${REMOTE_RETENTION_DAYS} days"
CUTOFF_DATE=$(date -u -d "-${REMOTE_RETENTION_DAYS} days" +%Y-%m-%dT%H-%M-%S 2>/dev/null || \
              date -u -v-"${REMOTE_RETENTION_DAYS}"d +%Y-%m-%dT%H-%M-%S 2>/dev/null || echo "")

if [ -n "${CUTOFF_DATE}" ]; then
    mc ls "${MINIO_ALIAS}/${MINIO_BUCKET}/" 2>/dev/null | while read -r line; do
        fname=$(echo "${line}" | awk '{print $NF}')
        # extract timestamp from filename
        file_ts=$(echo "${fname}" | sed -n 's/^loom-\(.*\)\.dump\.gz.*$/\1/p')
        if [ -n "${file_ts}" ] && [ "${file_ts}" \< "${CUTOFF_DATE}" ]; then
            log "removing expired remote backup: ${fname}"
            mc rm "${MINIO_ALIAS}/${MINIO_BUCKET}/${fname}" 2>/dev/null || true
        fi
    done
fi

log "backup complete: ${BACKUP_FILE}"
exit 0
