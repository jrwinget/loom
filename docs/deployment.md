# Deployment

This page covers the local-development bring-up of the
**server profile**. For the production checklist (TLS,
secrets, observability, Temporal production config, backup
rotation) see [`prod-deploy.md`](prod-deploy.md). For the
single-laptop install see [`desktop-lite.md`](desktop-lite.md).

## Local development

```bash
cp .env.example .env             # populate required vars
make up                          # start postgres, minio, temporal
cd backend && uv sync --all-extras && cd ..
cd frontend && pnpm install && cd ..
make migrate                     # run database migrations
make dev                         # start backend + frontend
```

The compose stack refuses to start without the credentials
listed under [Required environment variables](#required-environment-variables)
populated in `.env`. The example file ships sensible dev
sentinels — you can copy the file as-is for local
development, but production must override every credential
row.

### Services

| Service       | Port | URL                              |
| ------------- | ---- | -------------------------------- |
| Backend API   | 8000 | <http://localhost:8000/docs>     |
| Frontend      | 3000 | <http://localhost:3000>          |
| PostgreSQL    | 5432 | -                                |
| MinIO API     | 9000 | -                                |
| MinIO Console | 9001 | <http://localhost:9001>          |
| Temporal      | 7233 | -                                |
| Temporal UI   | 8080 | <http://localhost:8080>          |
| Grafana       | 3001 | <http://localhost:3001>          |

Grafana, Prometheus, and Jaeger only run under the
`observability` compose profile (`docker compose
--profile observability up`).

### Required environment variables

These four must be set in `.env`; compose fails fast
otherwise:

- `LOOM_SECRET_KEY` — JWT signing key, ≥32 chars; the
  literal `change-me-in-production` is rejected at startup
- `POSTGRES_PASSWORD` — Postgres password
- `MINIO_ROOT_USER` — MinIO access key
- `MINIO_ROOT_PASSWORD` — MinIO secret key

When the `observability` profile is active, also required:

- `GRAFANA_ADMIN_PASSWORD`

The backend additionally rejects the dev sentinel values
(`loom:loom_dev@` in the database URL, `loom_minio`,
`loom_minio_dev`) when running with `LOOM_DEBUG=false` and
`LOOM_DEPLOYMENT_PROFILE=server`. See
[`security.md`](security.md#production-credential-enforcement).

### Backend configuration

All backend variables are prefixed `LOOM_`. See
`.env.example` for the full list and
`backend/src/loom/config.py` for defaults and validators.

Key variables:

- `LOOM_DEPLOYMENT_PROFILE` — `server` (default) or `lite`
- `LOOM_DATABASE_URL` — Postgres connection string for
  server, sqlite for Lite
- `LOOM_MINIO_ENDPOINT` — `host:port` (no scheme)
- `LOOM_MINIO_ACCESS_KEY` / `LOOM_MINIO_SECRET_KEY`
- `LOOM_TEMPORAL_HOST` — Temporal server address
- `LOOM_SECRET_KEY` — JWT signing key (mandatory)
- `LOOM_CORS_ORIGINS` — JSON list of allowed origins,
  e.g. `'["https://app.example.com"]'`. `*` is rejected;
  every entry must be an absolute http(s) origin.
- `LOOM_DEBUG` — bypasses production credential checks for
  dev convenience; **never set true in production**.

## Docker Compose

```bash
docker compose -f docker/docker-compose.yml --profile app up -d
docker compose -f docker/docker-compose.yml --profile app down
```

Profiles:

- `app` — backend, worker, frontend (the application stack)
- `production` — adds the nginx TLS terminator
- `backup` — adds the scheduled backup container
- `observability` — adds Prometheus, Grafana, Jaeger

## Production deployment

See [`prod-deploy.md`](prod-deploy.md) for the full
checklist. At a minimum, production must:

- Use strong, unique values for every credential listed
  above.
- Terminate TLS at nginx (TLS 1.3 only).
- Replace `temporalio/auto-setup` with `temporalio/server`
  and run proper schema migrations.
- Configure backup retention against MinIO object lock.
- Enable MFA on all user accounts.
- Stand up the observability profile and wire alerts to a
  pager (the Prometheus alert set is tracked in #32).

[`runbook.md`](runbook.md) covers operational procedures —
service restarts, disk management, debugging workflows,
emergency response.
