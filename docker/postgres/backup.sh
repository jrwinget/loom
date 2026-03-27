#!/usr/bin/env bash
set -euo pipefail

# loom postgres backup script
# uses pg_dump custom format, uploads to minio, manages retention

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

LOG_PREFIX="[loom-backup]"

log() { echo "${LOG_PREFIX} $(date -u +%Y-%m-%dT%H:%M:%SZ) $*"; }
log_error() { echo "${LOG_PREFIX} $(date -u +%Y-%m-%dT%H:%M:%SZ) ERROR: $*" >&2; }

cleanup() {
    unset PGPASSWORD
}
trap cleanup EXIT

# ensure backup directory exists
mkdir -p "${BACKUP_DIR}"

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

# ── upload to minio ─────────────────────────────────────────
log "configuring minio client"
mc alias set "${MINIO_ALIAS}" "${MINIO_ENDPOINT}" "${MINIO_ACCESS_KEY}" "${MINIO_SECRET_KEY}" --api S3v4 2>/dev/null

log "ensuring bucket '${MINIO_BUCKET}' exists"
mc mb --ignore-existing "${MINIO_ALIAS}/${MINIO_BUCKET}"

log "uploading ${BACKUP_FILE} to minio"
if mc cp "${BACKUP_PATH}" "${MINIO_ALIAS}/${MINIO_BUCKET}/${BACKUP_FILE}"; then
    log "upload complete"
else
    log_error "minio upload failed — local backup retained at ${BACKUP_PATH}"
    exit 1
fi

# ── local retention ─────────────────────────────────────────
log "pruning local backups older than ${LOCAL_RETENTION_DAYS} days"
find "${BACKUP_DIR}" -name "loom-*.dump.gz" -type f -mtime +"${LOCAL_RETENTION_DAYS}" -delete 2>/dev/null || true
LOCAL_COUNT=$(find "${BACKUP_DIR}" -name "loom-*.dump.gz" -type f | wc -l)
log "local backups remaining: ${LOCAL_COUNT}"

# ── remote retention ────────────────────────────────────────
log "pruning remote backups older than ${REMOTE_RETENTION_DAYS} days"
CUTOFF_DATE=$(date -u -d "-${REMOTE_RETENTION_DAYS} days" +%Y-%m-%dT%H-%M-%S 2>/dev/null || \
              date -u -v-"${REMOTE_RETENTION_DAYS}"d +%Y-%m-%dT%H-%M-%S 2>/dev/null || echo "")

if [ -n "${CUTOFF_DATE}" ]; then
    mc ls "${MINIO_ALIAS}/${MINIO_BUCKET}/" 2>/dev/null | while read -r line; do
        fname=$(echo "${line}" | awk '{print $NF}')
        # extract timestamp from filename: loom-YYYY-MM-DDTHH-MM-SS.dump.gz
        file_ts=$(echo "${fname}" | sed -n 's/^loom-\(.*\)\.dump\.gz$/\1/p')
        if [ -n "${file_ts}" ] && [ "${file_ts}" \< "${CUTOFF_DATE}" ]; then
            log "removing expired remote backup: ${fname}"
            mc rm "${MINIO_ALIAS}/${MINIO_BUCKET}/${fname}" 2>/dev/null || true
        fi
    done
fi

log "backup complete: ${BACKUP_FILE}"
exit 0
