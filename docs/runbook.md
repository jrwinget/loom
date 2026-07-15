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

5. **Notify affected parties** per your organization's incident
   response procedures.

## Cutting a Release

`scripts/cut-release.sh` encodes the process so the footguns from
past releases can't recur (asset-append contamination, an unbumped
OpenAPI schema drifting the contract, tagging before the release PR
merged). Two steps, with a human-reviewed PR between them.

```bash
# 1. write the notes first — the script refuses to prepare without
#    a non-empty docs/release-notes/vX.Y.Z.md
$EDITOR docs/release-notes/v0.2.2.md

# 2. on a clean dev, prepare: bumps all five version files,
#    regenerates the version-embedding openapi + generated types,
#    verifies version lockstep, and leaves a release/v0.2.2 branch
#    with the bump commit
git switch dev && git pull
scripts/cut-release.sh prepare 0.2.2

# 3. push, open a PR to main, let the FULL check set pass, and
#    squash-merge it as "Release v0.2.2: <summary>"
git push -u origin release/v0.2.2

# 4. after the PR merges, tag: verifies main actually carries the
#    version and the notes, then creates and pushes the annotated
#    tag that triggers the installer + updater-manifest build
scripts/cut-release.sh tag 0.2.2

# 5. publish the notes body (the workflow only attaches assets)
gh release create v0.2.2 --verify-tag --title v0.2.2 \
  --notes-file docs/release-notes/v0.2.2.md
```

The `Desktop` workflow's **Release Guard** job refuses to build on a
tag whose release page already has assets, so a second run can never
append onto a populated release. A deliberate rebuild goes through
`workflow_dispatch`, or delete the release's assets first (see the
re-cut procedure below).

### Code-signing status

Three separate signing concerns exist, and only one is active:

- **Updater signatures (active, required).** `TAURI_SIGNING_PRIVATE_KEY`
  and `TAURI_SIGNING_PRIVATE_KEY_PASSWORD` minisign the updater
  artifacts (`.AppImage`, `.app.tar.gz`, `-setup.exe`) against the
  pubkey pinned in `tauri.conf.json`. Release Guard fails a tag build
  immediately if they are missing. Dependabot/fork PR runs have no
  secrets and build with updater artifacts disabled instead.
- **macOS codesign + notarization (NOT configured).** The dmg/app
  artifacts ship unsigned and un-notarized; users need the
  right-click-Open ritual and Gatekeeper may kill the bundled
  sidecar on Apple Silicon. The workflow step exists and activates
  when `APPLE_SIGNING_IDENTITY`, `APPLE_ID`, `APPLE_TEAM_ID`, and
  `APPLE_PASSWORD` are set (needs a Developer ID certificate).
  Tracked in #349.
- **Windows Authenticode (NOT configured).** The msi/nsis installers
  ship unsigned, so SmartScreen warns and Defender may quarantine
  the extracted sidecar. The workflow step activates when
  `WINDOWS_CERT_BASE64` and `WINDOWS_CERT_PASSWORD` are set.
  Tracked in #350.

The macOS/Windows skips are silent by design (`continue-on-error`
notices in the job log are the only trace) — check the job log for
"signing skipped" before assuming a release was signed.

**Decision (2026-07-15):** OS code signing is deliberately not
funded — Loom is an unfunded open-source project and both Apple and
Windows certificates are paid, recurring subscriptions. The
compensating controls are: a `SHA256SUMS` file attached to every
release (generated in the publish job), minisign-verified in-app
updates, and plain-language notices at every point users meet the OS
warnings (README, `docs/desktop-lite.md`, the first-run welcome, and
the update banner). The env-gated signing steps stay in the workflow;
if funding ever materializes, setting the secrets reactivates them —
note the onedir sidecar tree will then need a per-Mach-O signing pass
(see the notes on the closed signing issues #349/#350).

## Desktop Hotfix Release

The `Desktop` workflow attaches artifacts to a tag-named GitHub
release via `softprops/action-gh-release@v2`, which **appends** to
an existing release rather than replacing its assets. If a workflow
rerun (or a manual artifact upload) leaves stale files behind --
for example, multiple version-stamped binaries from different tags
mixed on one release page -- use this procedure to publish a clean
re-cut.

This was the exact failure mode behind the v0.1.1 boot-hang
remediation: the v0.1.1 release page accumulated assets from a
reverted v0.1.2 release after the workflow's append semantics
attached them, and from a stale v0.1.0 rebuild. The root cause
turned out to be the cargo cache restoring
`desktop/src-tauri/target/release/bundle/` from earlier runs --
the upload globs (`*.deb`, `*.exe`, `*.msi`) then matched every
artifact ever built. The "Purge cached Tauri bundles" step in
`.github/workflows/desktop.yml` (added in the v0.1.1 follow-up)
clears that directory before every build, so future re-cuts
should not need this runbook for the same reason. It remains the
canonical procedure if a release page ever drifts again.

### Preconditions

1. The fix branches have merged to `main` and CI is green on `main`
   (including the new sidecar smoke step on all three OS matrix
   entries).
2. You have write access to the repository and to the tag namespace
   -- check `gh api repos/{owner}/{repo}/rulesets` returns no tag
   protection for the tag you intend to force-move.

### Re-cut procedure

```bash
# 1. confirm the new main HEAD is what you intend to ship
git fetch origin main
git log origin/main -1 --oneline

# 2. delete the contaminated release, keeping the tag pinned so the
#    old SHA remains reachable for forensics
gh release delete v0.1.1 --yes --cleanup-tag=false

# 3. force-move the tag to the new HEAD
git tag -f v0.1.1 origin/main
git push origin v0.1.1 --force

# 4. the Desktop workflow re-runs on the tag push and creates a
#    fresh release. wait for it -- expect ~15 minutes for the
#    matrix to finish.
gh run watch $(gh run list --workflow=desktop.yml --limit 1 \
  --json databaseId --jq '.[0].databaseId')

# 5. verify the release contains only the expected artifacts (one
#    per matrix bundle target: deb, AppImage, msi, exe, dmg)
gh release view v0.1.1 --json assets --jq '.assets[].name'

# 6. update the release body to reflect the hotfix scope
gh release edit v0.1.1 --notes-file docs/release-notes/v0.1.1.md
```

### Verification on real hardware

Before announcing the hotfix, install one artifact per OS and
confirm the desktop bundle now boots:

- **Linux** (`Loom_0.1.1_amd64.deb`): `sudo dpkg -i Loom_*.deb &&
  loom`. The main window must open within ~2 s. The GTK "Wait or
  Force Quit" dialog must NOT appear during cold-start.
- **Windows** (`Loom_0.1.1_x64-setup.exe`): install, launch from
  Start menu. Title bar must read `Loom`, never
  `Loom (Not Responding)`.
- **macOS arm64** (`Loom_0.1.1_aarch64.dmg`): mount, drag to
  Applications, launch. Main window opens, boot panel transitions
  to app.

Intel-Mac (`x86_64-apple-darwin`) is a known gap in v0.1.1 -- the
workflow matrix only includes `macos-latest`, which resolves to
Apple Silicon. Adding a `macos-13` matrix entry is tracked for
v0.1.2.

### When this happens to a future release

The append-vs-replace behaviour of `softprops/action-gh-release@v2`
is a footgun on every release, not just v0.1.1. Until the workflow
adopts `make_latest: true` plus an explicit delete-then-attach
step, treat the runbook above as the canonical re-cut procedure for
*any* release whose asset list shows mixed versions.
