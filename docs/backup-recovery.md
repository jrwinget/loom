# Backup and Recovery

## Overview

Loom uses a defense-in-depth backup strategy with both local and
remote (MinIO) copies. Daily `pg_dump` backups are the default;
WAL archiving is documented for production deployments that need
point-in-time recovery.

**RPO/RTO targets:**

| Strategy | RPO | RTO |
|---|---|---|
| Daily pg_dump (default) | 24 hours | 30 minutes |
| WAL archiving (production) | ~5 minutes | 30 minutes |

## How Automated Backups Work

The `backup` Docker Compose profile runs a sidecar container
that:

1. Runs `pg_dump` in custom format, piped through gzip
2. Saves to a local Docker volume (`backup-data`)
3. Uploads to the `loom-backups` MinIO bucket
4. Prunes local backups older than 7 days
5. Prunes remote backups older than 30 days
6. Runs once on startup, then every 24 hours

Start the backup scheduler alongside other services:

```bash
docker compose -f docker/docker-compose.yml --profile backup up -d
```

## Manual Backup

Trigger a one-off backup:

```bash
make backup
```

This runs the backup script in an ephemeral container, producing
a timestamped dump file (`loom-YYYY-MM-DDTHH-MM-SS.dump.gz`)
stored locally and uploaded to MinIO.

## Restoring from Backup

### List Available Backups

```bash
# from inside a container with the restore script mounted:
docker compose -f docker/docker-compose.yml run --rm \
  --entrypoint /bin/sh postgres:16-alpine -c \
  "/scripts/restore.sh --list"
```

### Restore Latest Backup

The restore script includes interactive confirmation. It will
show which database will be overwritten, the backup source, and
the current table count before prompting you to type `yes`.

```bash
make restore
```

### Restore a Specific Backup

```bash
make restore FILE=loom-2025-01-15T12-00-00.dump.gz
```

### Step-by-Step Manual Restore

1. Stop the application to prevent writes:
   ```bash
   make down
   # restart only postgres and minio
   docker compose -f docker/docker-compose.yml up -d postgres minio minio-setup
   ```

2. Wait for services to be healthy:
   ```bash
   docker compose -f docker/docker-compose.yml ps
   ```

3. Run the restore:
   ```bash
   make restore FILE=loom-2025-01-15T12-00-00.dump.gz
   ```

4. Verify the restore:
   ```bash
   make verify-backup
   ```

5. Restart all services:
   ```bash
   make up
   ```

## Verifying Backups

Run the verification script to restore the latest backup to a
temporary database and check integrity:

```bash
make verify-backup
```

The script:
- Creates a temporary database (`loom_backup_verify`)
- Restores the latest backup into it
- Checks that expected tables exist (`users`, `cases`, `assets`,
  `audit_log`)
- Compares table counts with production
- Verifies audit_log is non-empty (if production has data)
- Drops the temporary database
- Reports PASS or FAIL

Run this weekly at minimum. In production, schedule it via cron.

## WAL Archiving (Production)

For production deployments requiring RPO under 24 hours, set up
continuous WAL archiving for point-in-time recovery (PITR).

### PostgreSQL Configuration

Add to `postgresql.conf` (or via Docker environment/config):

```ini
wal_level = replica
archive_mode = on
archive_command = 'mc cp %p loom/loom-wal-archive/%f'
archive_timeout = 300
```

### MinIO Setup

Create a dedicated WAL archive bucket:

```bash
mc mb loom/loom-wal-archive
mc anonymous set none loom/loom-wal-archive
```

### Point-in-Time Recovery

1. Stop PostgreSQL
2. Restore the latest base backup (pg_dump)
3. Create a `recovery.signal` file in the data directory
4. Configure `restore_command` in `postgresql.conf`:
   ```ini
   restore_command = 'mc cp loom/loom-wal-archive/%f %p'
   recovery_target_time = '2025-01-15 14:30:00 UTC'
   ```
5. Start PostgreSQL; it will replay WAL files up to the target
6. Once satisfied, run `SELECT pg_wal_replay_resume();`

### Production WAL Archiving Checklist

- [ ] Set `wal_level = replica` in PostgreSQL config
- [ ] Configure `archive_command` to upload to MinIO/S3
- [ ] Set `archive_timeout = 300` (5 min max data loss)
- [ ] Monitor archive lag (alert if WAL files queue)
- [ ] Test PITR monthly
- [ ] Retain WAL archives for at least 7 days
- [ ] Use a separate MinIO bucket for WAL vs. base backups

## Disaster Recovery Procedure

### Total Loss (Database + Local Volume)

1. Provision new PostgreSQL instance
2. Download latest backup from MinIO:
   ```bash
   mc cp loom/loom-backups/loom-LATEST.dump.gz ./
   ```
3. Create database and extensions:
   ```sql
   CREATE DATABASE loom;
   \c loom
   CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
   CREATE EXTENSION IF NOT EXISTS "pgcrypto";
   CREATE EXTENSION IF NOT EXISTS "pg_trgm";
   ```
4. Restore:
   ```bash
   gunzip -c loom-LATEST.dump.gz | pg_restore \
     -h HOST -U loom -d loom \
     --no-owner --no-acl --single-transaction
   ```
5. Run pending migrations:
   ```bash
   cd backend && uv run alembic upgrade head
   ```
6. Verify data integrity manually
7. Restart application services

### Partial Loss (Corrupted Table)

1. Take a fresh backup of current state (for safety)
2. Restore specific tables from backup using `pg_restore -t`:
   ```bash
   gunzip -c BACKUP.dump.gz | pg_restore \
     -h HOST -U loom -d loom \
     --no-owner --no-acl \
     -t TABLE_NAME --data-only
   ```

## Configuration Reference

| Variable | Default | Description |
|---|---|---|
| `POSTGRES_USER` | `loom` | Database user |
| `POSTGRES_PASSWORD` | `loom_dev` | Database password |
| `POSTGRES_DB` | `loom` | Database name |
| `MINIO_ROOT_USER` | `loom_minio` | MinIO access key |
| `MINIO_ROOT_PASSWORD` | `loom_minio_dev` | MinIO secret key |
| `MINIO_BACKUP_BUCKET` | `loom-backups` | MinIO bucket for backups |
| `LOCAL_RETENTION_DAYS` | `7` | Days to keep local backups |
| `REMOTE_RETENTION_DAYS` | `30` | Days to keep remote backups |
| `BACKUP_DIR` | `/backups` | Local backup directory in container |
