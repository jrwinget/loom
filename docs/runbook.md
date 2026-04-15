# Loom Operational Runbook

## Service Restart Procedures

### Single service restart

```bash
docker compose -f docker/docker-compose.yml restart <service>
```

Services: `postgres`, `minio`, `temporal`, `backend`, `worker`, `frontend`, `nginx`.

### Full stack restart (preserves data)

```bash
docker compose -f docker/docker-compose.yml --profile app down
docker compose -f docker/docker-compose.yml --profile app up -d
```

### Temporal restart (stuck workflows)

```bash
docker compose -f docker/docker-compose.yml restart temporal
docker compose -f docker/docker-compose.yml restart worker
```

Wait for Temporal healthcheck to pass before restarting the worker.

## Database Disk Full

1. Check disk usage:
   ```bash
   docker exec loom-postgres-1 df -h /var/lib/postgresql/data
   ```

2. Identify large tables:
   ```sql
   SELECT relname, pg_size_pretty(pg_total_relation_size(oid))
   FROM pg_class WHERE relkind = 'r'
   ORDER BY pg_total_relation_size(oid) DESC LIMIT 10;
   ```

3. Prune old audit_log entries (audit_log is append-only, but archiving old rows is acceptable):
   ```sql
   -- export first
   COPY (SELECT * FROM audit_log WHERE created_at < now() - interval '90 days')
     TO '/tmp/audit_archive.csv' CSV HEADER;
   DELETE FROM audit_log WHERE created_at < now() - interval '90 days';
   VACUUM FULL audit_log;
   ```

4. If PostgreSQL WAL is the culprit:
   ```bash
   docker exec loom-postgres-1 psql -U loom -c "SELECT pg_size_pretty(sum(size)) FROM pg_ls_waldir();"
   ```
   Force a checkpoint: `CHECKPOINT;` then verify WAL shrinks.

5. Expand the volume if needed:
   ```bash
   docker volume inspect loom_postgres-data
   ```

## High Memory / OOM Handling

1. Identify the offending container:
   ```bash
   docker stats --no-stream --format "table {{.Name}}\t{{.MemUsage}}\t{{.MemPerc}}"
   ```

2. Common culprits:
   - **worker**: AI processing (transcription, OCR, scene detection) uses significant memory. Scale horizontally instead of vertically.
   - **postgres**: Increase `shared_buffers` or reduce `work_mem` if sort spills.
   - **temporal**: Increase memory limit; check for workflow history bloat.

3. Set memory limits in docker-compose override:
   ```yaml
   services:
     worker:
       deploy:
         resources:
           limits:
             memory: 4G
   ```

4. Restart the OOM-killed container:
   ```bash
   docker compose -f docker/docker-compose.yml restart <service>
   ```

## Debugging Slow Queries

1. Enable slow query logging:
   ```sql
   ALTER SYSTEM SET log_min_duration_statement = 500;  -- ms
   SELECT pg_reload_conf();
   ```

2. Check active queries:
   ```sql
   SELECT pid, now() - query_start AS duration, state, query
   FROM pg_stat_activity
   WHERE state != 'idle'
   ORDER BY duration DESC;
   ```

3. Kill a runaway query:
   ```sql
   SELECT pg_cancel_backend(<pid>);    -- graceful
   SELECT pg_terminate_backend(<pid>); -- forced
   ```

4. Check for missing indexes:
   ```sql
   SELECT relname, seq_scan, idx_scan,
          pg_size_pretty(pg_relation_size(relid))
   FROM pg_stat_user_tables
   WHERE seq_scan > 1000 AND idx_scan < 100
   ORDER BY seq_scan DESC;
   ```

5. Check for lock contention:
   ```sql
   SELECT blocked.pid, blocked.query, blocking.pid AS blocking_pid
   FROM pg_stat_activity blocked
   JOIN pg_locks bl ON bl.pid = blocked.pid
   JOIN pg_locks kl ON kl.locktype = bl.locktype
     AND kl.relation = bl.relation AND kl.pid != bl.pid
   JOIN pg_stat_activity blocking ON blocking.pid = kl.pid
   WHERE NOT bl.granted;
   ```

## Debugging Failed Temporal Workflows

1. Open the Temporal UI: `http://localhost:8080`

2. Filter by workflow type (`IngestWorkflow`, `ExportWorkflow`, `TranscriptionWorkflow`, `OCRWorkflow`, `SceneDetectionWorkflow`) and status `Failed`.

3. Inspect the event history to find the failed activity.

4. Common failures:
   - **Connection refused to MinIO**: check MinIO healthcheck, restart if needed.
   - **Database timeout**: check PostgreSQL connection pool (`LOOM_DB_POOL_SIZE`).
   - **OOM during transcription**: reduce batch size or scale workers.
   - **File not found**: verify the asset exists in MinIO originals bucket.

5. Retry a failed workflow from the Temporal UI (click "Reset" on the failed activity).

6. Check worker logs:
   ```bash
   docker compose -f docker/docker-compose.yml logs worker --tail 200 -f
   ```

## Manual Backup and Verification

### Run a backup

```bash
docker compose -f docker/docker-compose.yml --profile backup run --rm backup /scripts/backup.sh
```

### List available backups

```bash
docker compose -f docker/docker-compose.yml --profile backup run --rm \
  -v ./docker/postgres/restore.sh:/scripts/restore.sh:ro \
  backup /scripts/restore.sh --list
```

### Verify a backup

```bash
# restore to a temporary database
docker exec loom-postgres-1 psql -U loom -c "CREATE DATABASE loom_verify;"
docker exec loom-postgres-1 bash -c \
  "gunzip -c /backups/<backup-file> | pg_restore -U loom -d loom_verify --no-owner"

# check key tables
docker exec loom-postgres-1 psql -U loom -d loom_verify -c \
  "SELECT 'users' AS t, count(*) FROM users
   UNION ALL SELECT 'cases', count(*) FROM cases
   UNION ALL SELECT 'assets', count(*) FROM assets;"

# clean up
docker exec loom-postgres-1 psql -U loom -c "DROP DATABASE loom_verify;"
```

### Restore from backup

```bash
docker compose -f docker/docker-compose.yml --profile backup run --rm \
  -v ./docker/postgres/restore.sh:/scripts/restore.sh:ro \
  backup /scripts/restore.sh --confirm [BACKUP_FILE]
```

## Scaling Workers

Workers are stateless and can be scaled horizontally.

### Scale with docker compose

```bash
docker compose -f docker/docker-compose.yml --profile app up -d --scale worker=3
```

### Monitor worker load

- Check Temporal UI for task queue backlog.
- Check Prometheus metrics at `http://localhost:9090` for `loom_activity_duration_seconds`.

### Right-sizing

- **Transcription**: CPU-heavy, 1 worker per 2 CPU cores.
- **OCR**: CPU-heavy, similar to transcription.
- **Scene detection**: CPU + memory, 1 worker per 4GB RAM.
- **Ingest (hash/metadata/proxy)**: I/O-bound, can run more workers per core.

## Emergency Procedures

### Data Corruption

1. **Stop writes immediately**:
   ```bash
   docker compose -f docker/docker-compose.yml --profile app stop backend worker
   ```

2. **Assess the damage**:
   ```sql
   -- check for inconsistent chain of custody
   SELECT a.id FROM assets a
   LEFT JOIN chain_of_custody_entries c ON c.asset_id = a.id
   WHERE c.id IS NULL;

   -- check for orphaned derivatives
   SELECT d.id FROM derivatives d
   LEFT JOIN assets a ON a.id = d.asset_id
   WHERE a.id IS NULL;
   ```

3. **Restore from the most recent verified backup** (see Manual Backup section above).

4. **Verify MinIO originals are intact**:
   ```bash
   docker exec loom-minio-1 mc ls local/loom-originals/ | wc -l
   ```

5. **Restart services and monitor**:
   ```bash
   docker compose -f docker/docker-compose.yml --profile app up -d
   docker compose -f docker/docker-compose.yml logs -f backend worker
   ```

### Security Breach

1. **Rotate secrets immediately**:
   - `LOOM_SECRET_KEY` (invalidates all JWTs)
   - `POSTGRES_PASSWORD`
   - `MINIO_ROOT_USER` / `MINIO_ROOT_PASSWORD`
   - Update `.env` and restart all services.

2. **Revoke all active sessions**:
   ```sql
   INSERT INTO revoked_tokens (jti, revoked_at)
   SELECT jti, now() FROM active_sessions;  -- if tracked
   ```

3. **Review audit log for unauthorized access**:
   ```sql
   SELECT * FROM audit_log
   WHERE created_at > now() - interval '24 hours'
   ORDER BY created_at DESC;
   ```

4. **Check for unauthorized data export**:
   ```sql
   SELECT * FROM export_bundles
   WHERE created_at > now() - interval '24 hours';
   ```

5. **Notify affected parties** per NLG incident response procedures.
