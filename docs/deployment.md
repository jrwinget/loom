# Deployment

## Local Development

```bash
cp .env.example .env
make up           # start postgres, minio, temporal
make dev          # start backend + frontend dev servers
```

### Services

| Service | Port | URL |
|---------|------|-----|
| Backend API | 8000 | http://localhost:8000/docs |
| Frontend | 3000 | http://localhost:3000 |
| PostgreSQL | 5432 | - |
| MinIO API | 9000 | - |
| MinIO Console | 9001 | http://localhost:9001 |
| Temporal | 7233 | - |
| Temporal UI | 8080 | http://localhost:8080 |

### Environment Variables

All backend configuration uses the `LOOM_` prefix. See
`.env.example` for the full list.

Key variables:
- `LOOM_DATABASE_URL` — PostgreSQL connection string
- `LOOM_MINIO_ENDPOINT` — MinIO host:port
- `LOOM_MINIO_ACCESS_KEY` / `LOOM_MINIO_SECRET_KEY`
- `LOOM_TEMPORAL_HOST` — Temporal server address
- `LOOM_SECRET_KEY` — JWT signing key (change in production)

## Docker Compose

The `docker/docker-compose.yml` defines all infrastructure
services. The override file adds development-specific port
mappings.

```bash
docker compose -f docker/docker-compose.yml up -d
docker compose -f docker/docker-compose.yml down
```

## Production Considerations

- Use a strong, random `LOOM_SECRET_KEY` (minimum 32 bytes)
- Enable TLS on all services
- Use external PostgreSQL with backups
- Configure MinIO with replication and encryption at rest
- Set `LOOM_MINIO_SECURE=true` for HTTPS
- Run Temporal with a production database backend
- Set up log aggregation (OpenTelemetry → Grafana stack)
- Enable MFA for all user accounts
- Configure backup retention for MinIO object lock
