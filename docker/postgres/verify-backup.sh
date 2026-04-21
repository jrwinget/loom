#!/usr/bin/env bash
set -euo pipefail

# loom backup verification script
# restores latest backup to a temporary database and runs integrity checks

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

VERIFY_DB="loom_backup_verify"

LOG_PREFIX="[loom-verify]"
PASS=true

log() { echo "${LOG_PREFIX} $(date -u +%Y-%m-%dT%H:%M:%SZ) $*"; }
log_error() { echo "${LOG_PREFIX} $(date -u +%Y-%m-%dT%H:%M:%SZ) ERROR: $*" >&2; }

cleanup() {
    log "dropping temporary database '${VERIFY_DB}'"
    psql -h "${PGHOST}" -p "${PGPORT}" -U "${PGUSER}" -d "postgres" -c \
        "DROP DATABASE IF EXISTS ${VERIFY_DB};" 2>/dev/null || true
    unset PGPASSWORD
}
trap cleanup EXIT

# ── find latest backup ──────────────────────────────────────
BACKUP_FILE=$(ls -1t "${BACKUP_DIR}"/loom-*.dump.gz 2>/dev/null | head -1 || true)

if [ -z "${BACKUP_FILE}" ]; then
    log "no local backup found, checking minio"
    mc alias set "${MINIO_ALIAS}" "${MINIO_ENDPOINT}" "${MINIO_ACCESS_KEY}" "${MINIO_SECRET_KEY}" --api S3v4 2>/dev/null

    REMOTE_FILE=$(mc ls "${MINIO_ALIAS}/${MINIO_BUCKET}/" 2>/dev/null \
        | grep "loom-.*\.dump\.gz" \
        | awk '{print $NF}' \
        | sort -r \
        | head -1 || true)

    if [ -z "${REMOTE_FILE}" ]; then
        log_error "no backups found locally or in minio"
        exit 1
    fi

    mkdir -p "${BACKUP_DIR}"
    log "downloading ${REMOTE_FILE} from minio"
    mc cp "${MINIO_ALIAS}/${MINIO_BUCKET}/${REMOTE_FILE}" "${BACKUP_DIR}/${REMOTE_FILE}"
    BACKUP_FILE="${BACKUP_DIR}/${REMOTE_FILE}"
fi

BACKUP_NAME=$(basename "${BACKUP_FILE}")
log "verifying backup: ${BACKUP_NAME}"

# ── create temporary database ───────────────────────────────
log "creating temporary database '${VERIFY_DB}'"
psql -h "${PGHOST}" -p "${PGPORT}" -U "${PGUSER}" -d "postgres" -c \
    "DROP DATABASE IF EXISTS ${VERIFY_DB};"
psql -h "${PGHOST}" -p "${PGPORT}" -U "${PGUSER}" -d "postgres" -c \
    "CREATE DATABASE ${VERIFY_DB};"

# enable extensions needed by loom
psql -h "${PGHOST}" -p "${PGPORT}" -U "${PGUSER}" -d "${VERIFY_DB}" -c \
    "CREATE EXTENSION IF NOT EXISTS \"uuid-ossp\";
     CREATE EXTENSION IF NOT EXISTS \"pgcrypto\";
     CREATE EXTENSION IF NOT EXISTS \"pg_trgm\";"

# ── restore to temporary database ───────────────────────────
log "restoring backup to temporary database"
if gunzip -c "${BACKUP_FILE}" | pg_restore \
    -h "${PGHOST}" \
    -p "${PGPORT}" \
    -U "${PGUSER}" \
    -d "${VERIFY_DB}" \
    --no-owner \
    --no-acl 2>&1; then
    log "restore to temporary database succeeded"
else
    log "pg_restore completed with warnings (checking integrity)"
fi

# ── integrity checks ────────────────────────────────────────
log "running integrity checks"

# check 1: tables exist
TABLE_COUNT=$(psql -h "${PGHOST}" -p "${PGPORT}" -U "${PGUSER}" -d "${VERIFY_DB}" -tAc \
    "SELECT count(*) FROM information_schema.tables WHERE table_schema = 'public';")
log "check: public tables found: ${TABLE_COUNT}"
if [ "${TABLE_COUNT}" -lt 1 ]; then
    log_error "FAIL — no tables found in restored backup"
    PASS=false
fi

# check 2: key tables present
KEY_TABLES="users cases assets audit_log"
for table in ${KEY_TABLES}; do
    exists=$(psql -h "${PGHOST}" -p "${PGPORT}" -U "${PGUSER}" -d "${VERIFY_DB}" -tAc \
        "SELECT EXISTS (SELECT 1 FROM information_schema.tables
         WHERE table_schema = 'public' AND table_name = '${table}');" 2>/dev/null || echo "f")
    if [ "${exists}" = "t" ]; then
        count=$(psql -h "${PGHOST}" -p "${PGPORT}" -U "${PGUSER}" -d "${VERIFY_DB}" -tAc \
            "SELECT count(*) FROM ${table};" 2>/dev/null || echo "0")
        log "check: ${table} exists, rows: ${count}"
    else
        log_error "FAIL — expected table '${table}' not found"
        PASS=false
    fi
done

# check 3: compare table counts with production
PROD_TABLE_COUNT=$(psql -h "${PGHOST}" -p "${PGPORT}" -U "${PGUSER}" -d "${PGDATABASE}" -tAc \
    "SELECT count(*) FROM information_schema.tables WHERE table_schema = 'public';" 2>/dev/null || echo "0")
log "check: production tables: ${PROD_TABLE_COUNT}, backup tables: ${TABLE_COUNT}"
if [ "${TABLE_COUNT}" -lt "${PROD_TABLE_COUNT}" ]; then
    log_error "WARNING — backup has fewer tables than production (${TABLE_COUNT} < ${PROD_TABLE_COUNT})"
fi

# check 4: audit_log is non-empty (if production has data)
PROD_AUDIT=$(psql -h "${PGHOST}" -p "${PGPORT}" -U "${PGUSER}" -d "${PGDATABASE}" -tAc \
    "SELECT count(*) FROM audit_log;" 2>/dev/null || echo "0")
VERIFY_AUDIT=$(psql -h "${PGHOST}" -p "${PGPORT}" -U "${PGUSER}" -d "${VERIFY_DB}" -tAc \
    "SELECT count(*) FROM audit_log;" 2>/dev/null || echo "0")
if [ "${PROD_AUDIT}" -gt 0 ] && [ "${VERIFY_AUDIT}" -eq 0 ]; then
    log_error "FAIL — audit_log is empty in backup but has ${PROD_AUDIT} rows in production"
    PASS=false
fi

# ── report ──────────────────────────────────────────────────
echo ""
if [ "${PASS}" = true ]; then
    log "RESULT: PASS — backup '${BACKUP_NAME}' verified successfully"
    exit 0
else
    log_error "RESULT: FAIL — backup '${BACKUP_NAME}' has integrity issues"
    exit 1
fi
