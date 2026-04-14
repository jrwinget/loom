#!/usr/bin/env bash
set -euo pipefail

# loom postgres restore script
# restores a pg_dump backup, optionally downloading from minio

BACKUP_DIR="${BACKUP_DIR:-/backups}"

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

LOG_PREFIX="[loom-restore]"

log() { echo "${LOG_PREFIX} $(date -u +%Y-%m-%dT%H:%M:%SZ) $*"; }
log_error() { echo "${LOG_PREFIX} $(date -u +%Y-%m-%dT%H:%M:%SZ) ERROR: $*" >&2; }

cleanup() {
    unset PGPASSWORD
}
trap cleanup EXIT

usage() {
    cat <<USAGE
Usage: $(basename "$0") [OPTIONS] [BACKUP_FILE]

Restore a Loom database backup.

Arguments:
  BACKUP_FILE   Backup filename (e.g. loom-2025-01-15T12-00-00.dump.gz)
                If omitted, restores the most recent backup.

Options:
  --confirm     Required flag to proceed with restore (safety guard)
  --list        List available backups (local and remote)
  --help        Show this help message

Examples:
  $(basename "$0") --list
  $(basename "$0") --confirm
  $(basename "$0") --confirm loom-2025-01-15T12-00-00.dump.gz
USAGE
    exit 0
}

# ── parse arguments ─────────────────────────────────────────
CONFIRM=false
LIST_ONLY=false
BACKUP_FILE=""

while [[ $# -gt 0 ]]; do
    case "$1" in
        --confirm) CONFIRM=true; shift ;;
        --list) LIST_ONLY=true; shift ;;
        --help|-h) usage ;;
        -*) log_error "unknown option: $1"; usage ;;
        *) BACKUP_FILE="$1"; shift ;;
    esac
done

# ── configure minio client ─────────────────────────────────
mc alias set "${MINIO_ALIAS}" "${MINIO_ENDPOINT}" "${MINIO_ACCESS_KEY}" "${MINIO_SECRET_KEY}" --api S3v4 2>/dev/null

# ── list mode ───────────────────────────────────────────────
if [ "${LIST_ONLY}" = true ]; then
    echo "Local backups (${BACKUP_DIR}):"
    ls -1t "${BACKUP_DIR}"/loom-*.dump.gz 2>/dev/null | head -20 || echo "  (none)"
    echo ""
    echo "Remote backups (minio/${MINIO_BUCKET}):"
    mc ls "${MINIO_ALIAS}/${MINIO_BUCKET}/" 2>/dev/null | grep "loom-.*\.dump\.gz" | tail -20 || echo "  (none)"
    exit 0
fi

# ── safety check ────────────────────────────────────────────
if [ "${CONFIRM}" != true ]; then
    log_error "restore requires --confirm flag to prevent accidental data loss"
    log_error "usage: $(basename "$0") --confirm [BACKUP_FILE]"
    exit 1
fi

# ── resolve backup file ────────────────────────────────────
if [ -z "${BACKUP_FILE}" ]; then
    log "no backup file specified — finding most recent"
    # prefer local, fall back to remote
    BACKUP_FILE=$(ls -1t "${BACKUP_DIR}"/loom-*.dump.gz 2>/dev/null | head -1 | xargs -r basename || true)

    if [ -z "${BACKUP_FILE}" ]; then
        log "no local backups found, checking minio"
        BACKUP_FILE=$(mc ls "${MINIO_ALIAS}/${MINIO_BUCKET}/" 2>/dev/null \
            | grep "loom-.*\.dump\.gz" \
            | awk '{print $NF}' \
            | sort -r \
            | head -1 || true)
    fi

    if [ -z "${BACKUP_FILE}" ]; then
        log_error "no backups found locally or in minio"
        exit 1
    fi
    log "selected backup: ${BACKUP_FILE}"
fi

BACKUP_PATH="${BACKUP_DIR}/${BACKUP_FILE}"

# ── download from minio if not local ───────────────────────
if [ ! -f "${BACKUP_PATH}" ]; then
    log "backup not found locally, downloading from minio"
    mkdir -p "${BACKUP_DIR}"
    if mc cp "${MINIO_ALIAS}/${MINIO_BUCKET}/${BACKUP_FILE}" "${BACKUP_PATH}"; then
        log "download complete"
    else
        log_error "failed to download ${BACKUP_FILE} from minio"
        exit 1
    fi
fi

# ── pre-restore table counts ───────────────────────────────
log "recording pre-restore state"
PRE_TABLES=$(psql -h "${PGHOST}" -p "${PGPORT}" -U "${PGUSER}" -d "${PGDATABASE}" -tAc \
    "SELECT count(*) FROM information_schema.tables WHERE table_schema = 'public';" 2>/dev/null || echo "0")
log "pre-restore public tables: ${PRE_TABLES}"

# ── restore ─────────────────────────────────────────────────
log "restoring ${BACKUP_FILE} to ${PGDATABASE} on ${PGHOST}:${PGPORT}"
log "WARNING: this will overwrite existing data in '${PGDATABASE}'"

# decompress and restore
if gunzip -c "${BACKUP_PATH}" | pg_restore \
    -h "${PGHOST}" \
    -p "${PGPORT}" \
    -U "${PGUSER}" \
    -d "${PGDATABASE}" \
    --clean \
    --if-exists \
    --no-owner \
    --no-acl \
    --single-transaction 2>&1; then
    log "pg_restore completed"
else
    # pg_restore returns non-zero on warnings too; check if db is usable
    log "pg_restore exited with warnings (this is often normal)"
fi

# ── post-restore verification ───────────────────────────────
log "verifying restore"

POST_TABLES=$(psql -h "${PGHOST}" -p "${PGPORT}" -U "${PGUSER}" -d "${PGDATABASE}" -tAc \
    "SELECT count(*) FROM information_schema.tables WHERE table_schema = 'public';" 2>/dev/null || echo "0")
log "post-restore public tables: ${POST_TABLES}"

if [ "${POST_TABLES}" -eq 0 ]; then
    log_error "restore verification failed — no tables found"
    exit 1
fi

# report row counts for key tables
KEY_TABLES="users cases assets annotations timeline_events audit_log"
log "row counts for key tables:"
for table in ${KEY_TABLES}; do
    count=$(psql -h "${PGHOST}" -p "${PGPORT}" -U "${PGUSER}" -d "${PGDATABASE}" -tAc \
        "SELECT count(*) FROM ${table};" 2>/dev/null || echo "n/a")
    log "  ${table}: ${count}"
done

log "restore complete from ${BACKUP_FILE}"
exit 0
