# Loom Production Deployment Guide

This guide covers deploying Loom to production using
open-source, self-hosted infrastructure — appropriate for a
civil-liberties organization handling sensitive legal evidence.

## Architecture Overview

```
Internet → Caddy/Nginx (TLS) → Frontend (React)
                              → Backend (FastAPI)
                              → MinIO (presigned URLs)

Backend → PostgreSQL (primary data)
       → Temporal (workflow orchestration)
       → MinIO (evidence storage, WORM)

Worker → Temporal (activity execution)
      → PostgreSQL
      → MinIO
```

---

## 1. Platform Selection

### Recommended: Docker Compose + systemd on a VPS

For a small team, start with Docker Compose on a single server.
Graduate to Coolify (GUI) or K3s (multi-node) when needed.

| Option | When to Use |
|--------|-------------|
| Docker Compose + systemd | Single server, 1-3 operators |
| Coolify | Team wants a GUI, auto-deploy from git |
| K3s | Need horizontal scaling of workers |

**Suggested providers** (EU data sovereignty, good for
civil-society orgs): Hetzner, OVH, Scaleway.

**Minimum server specs:**
- 4 vCPU, 8GB RAM, 100GB SSD (small deployment)
- 8 vCPU, 16GB RAM, 500GB SSD (medium, with video)

---

## 2. Secrets Management

### SOPS + age (zero infrastructure)

Never deploy with the default `.env.example` credentials.

```bash
# install
brew install sops age  # or apt install sops age

# generate keypair (store private key securely offline)
age-keygen -o key.txt
# outputs: public key: age1...

# encrypt production env file
sops --age age1... -e .env.production > .env.production.enc

# decrypt at deploy time
export SOPS_AGE_KEY_FILE=./key.txt
sops -d .env.production.enc > .env
```

Store `.env.production.enc` in git. Store `key.txt` offline
(USB drive in a safe, or a password manager).

### Docker Compose secrets (runtime)

For the most sensitive values, use the `secrets:` directive
instead of environment variables:

```yaml
secrets:
  loom_secret_key:
    file: ./secrets/loom_secret_key.txt
  postgres_password:
    file: ./secrets/postgres_password.txt

services:
  backend:
    secrets:
      - loom_secret_key
      - postgres_password
    environment:
      LOOM_SECRET_KEY_FILE: /run/secrets/loom_secret_key
```

---

## 3. TLS / HTTPS

### Option A: Caddy (simplest — automatic HTTPS)

Replace nginx with Caddy for automatic Let's Encrypt:

```
# Caddyfile
yourdomain.com {
    handle /api/* {
        reverse_proxy backend:8000
        request_body max_size 100MB
    }
    handle {
        reverse_proxy frontend:80
    }
    header {
        X-Frame-Options "DENY"
        X-Content-Type-Options "nosniff"
        Referrer-Policy "strict-origin-when-cross-origin"
    }
}
```

### Option B: Nginx + certbot

Use the included `nginx-tls.conf` with Let's Encrypt:

```bash
# install certbot
apt install certbot python3-certbot-nginx

# obtain certificate
certbot certonly --standalone -d yourdomain.com

# copy certs to mount path
cp /etc/letsencrypt/live/yourdomain.com/fullchain.pem \
   /path/to/docker/nginx/certs/
cp /etc/letsencrypt/live/yourdomain.com/privkey.pem \
   /path/to/docker/nginx/certs/

# mount nginx-tls.conf instead of nginx.conf
# in docker-compose.yml:
#   volumes:
#     - ./nginx/nginx-tls.conf:/etc/nginx/nginx.conf:ro
#     - ./nginx/certs:/etc/nginx/certs:ro
```

Set up auto-renewal via cron:
```bash
0 3 * * * certbot renew --quiet && docker restart nginx
```

---

## 4. Database

### Production PostgreSQL

**Connection pooling:** Use SQLAlchemy's built-in pool
(NOT PgBouncer — it breaks asyncpg prepared statements).

Recommended `config.py` production settings:
```
LOOM_DB_POOL_SIZE=9          # cpu_cores * 2 + 1
LOOM_DB_MAX_OVERFLOW=10
LOOM_DB_POOL_RECYCLE=1800    # 30 minutes
LOOM_DB_POOL_PRE_PING=true
```

**Backups:** The included `backup.sh` handles:
- `pg_isready` pre-check before dump
- `gunzip -t` integrity verification
- Optional GPG encryption (`BACKUP_GPG_RECIPIENT`)
- Retry logic (3 attempts with backoff)
- Local + remote retention policies

Enable encrypted backups:
```bash
# generate GPG key for backups
gpg --full-generate-key  # RSA 4096, no passphrase

# export public key
gpg --export -a "backup@yourdomain.com" > backup-key.pub

# set in .env
BACKUP_GPG_RECIPIENT=backup@yourdomain.com
```

**WAL archiving** (for point-in-time recovery):
```yaml
# add to postgres environment in docker-compose.yml
POSTGRES_INITDB_ARGS: "--wal-segsize=16"
# add to postgresql.conf (mount custom config)
archive_mode: "on"
archive_command: "mc cp %p loom/loom-wal-archive/%f"
```

### High Availability (when needed)

Use Patroni + etcd for automatic failover:
- Minimum 3 PostgreSQL nodes
- etcd cluster for consensus
- HAProxy or PgBouncer (session mode) as connection router

---

## 5. Object Storage (MinIO)

### Production configuration

**Single-server** (acceptable for small deployments):
- Use local RAID-1 or RAID-10 storage
- Enable TLS: place certs in `~/.minio/certs/`

**Distributed mode** (recommended for evidence integrity):
- Minimum 4 nodes with 4 drives each
- Erasure coding provides automatic redundancy
- Can lose up to 4 drives without data loss

**WORM / Object Lock** is already configured in
`docker-compose.yml` for `loom-originals`. Verify it's
active:
```bash
mc retention info loom/loom-originals
# should show: Mode: COMPLIANCE, Duration: 365 days
```

**Critical:** Remove `|| true` from the retention command
in minio-setup. If Object Lock fails, the system should not
proceed — evidence immutability is a core requirement.

---

## 6. Temporal

### Replace auto-setup with production server

The `temporalio/auto-setup` image is for development only.

For production:
1. Use `temporalio/server` image
2. Run schema migrations separately via init container
3. Use a dedicated PostgreSQL database for Temporal
4. Configure production dynamic config

```yaml
temporal:
  image: temporalio/server:1.25.2
  environment:
    DB: postgresql
    DB_PORT: 5432
    POSTGRES_USER: temporal
    POSTGRES_PWD: ${TEMPORAL_DB_PASSWORD}
    POSTGRES_SEEDS: postgres
    TEMPORAL_ADDRESS: temporal:7233
    DEFAULT_NAMESPACE: loom
    DYNAMIC_CONFIG_FILE_PATH: /etc/temporal/dynamicconfig/production.yaml
```

---

## 7. Monitoring

### Prometheus + Grafana + Loki + Uptime Kuma

Add to the `observability` profile in docker-compose:

```yaml
prometheus:
  image: prom/prometheus:v2.53.0
  volumes:
    - ./prometheus/prometheus.yml:/etc/prometheus/prometheus.yml:ro
  profiles: [observability]
  networks: [backend]

grafana:
  image: grafana/grafana:11.3.0
  volumes:
    - grafana-data:/var/lib/grafana
  profiles: [observability]
  networks: [backend]

loki:
  image: grafana/loki:3.3.0
  profiles: [observability]
  networks: [backend]
```

**FastAPI metrics:** Add `prometheus-fastapi-instrumentator`
to `pyproject.toml` and instrument in `main.py`:
```python
from prometheus_fastapi_instrumentator import Instrumentator
Instrumentator().instrument(application).expose(application)
```

**External uptime monitoring:** Deploy Uptime Kuma on a
SEPARATE server. Monitor `/api/v1/health` every 60 seconds
with alerts to Slack/Signal/email.

---

## 8. Host Security Hardening

### Firewall (nftables)

```bash
# allow only SSH, HTTP, HTTPS
nft add rule inet filter input tcp dport {22,80,443} accept
nft add rule inet filter input ct state established accept
nft add rule inet filter input drop
```

**Docker bypass warning:** Docker manipulates iptables
directly, bypassing nftables rules. Use the DOCKER-USER
chain or set `DOCKER_IPTABLES=false` and manage routing
manually.

### SSH hardening

```bash
# /etc/ssh/sshd_config
PermitRootLogin no
PasswordAuthentication no
PubkeyAuthentication yes
MaxAuthTries 3
```

Install Fail2ban:
```bash
apt install fail2ban
# configure /etc/fail2ban/jail.local
# banaction = nftables-multiport
```

### Container security

Add to each service in docker-compose.yml:
```yaml
security_opt:
  - no-new-privileges:true
cap_drop:
  - ALL
```

---

## 9. CI/CD Pipeline

### GitHub Actions deployment flow

```
PR → lint + test + scan → merge to main
                              ↓
                    build + push images
                              ↓
                    SSH → pull + migrate + restart
                              ↓
                    health check + smoke test
```

**Database migrations:** Use the expand-contract pattern:
1. Deploy "expand" migration (additive, backward-compatible)
2. Deploy new application code
3. Verify everything works
4. Deploy "contract" migration (remove old columns/tables)

Set `lock_timeout` in Alembic migrations to prevent blocking:
```python
op.execute("SET lock_timeout = '5s'")
```

---

## 10. Production Checklist

### Before first deployment

- [ ] Generate and store SOPS age keypair offline
- [ ] Create `.env.production` with strong, unique credentials
- [ ] Encrypt with SOPS and commit `.env.production.enc`
- [ ] Obtain TLS certificate (Let's Encrypt or CA)
- [ ] Verify MinIO Object Lock is active on `loom-originals`
- [ ] Set `LOOM_CORS_ORIGINS` to production domain(s)
- [ ] Set `LOOM_SECRET_KEY` to a random 64+ character string
- [ ] Enable GPG encryption for backups
- [ ] Configure firewall (nftables)
- [ ] Harden SSH (key-only, no root)
- [ ] Install and configure Fail2ban
- [ ] Set up external uptime monitoring
- [ ] Run `make verify-backup` to test backup/restore cycle
- [ ] Review and adjust Docker resource limits for your hardware
- [ ] Replace `temporalio/auto-setup` with `temporalio/server`
- [ ] Set up log aggregation (Loki + Promtail or similar)
- [ ] Document incident response runbook

### After deployment

- [ ] Verify health endpoint: `curl https://yourdomain.com/api/v1/health`
- [ ] Verify CSRF cookie is set on first GET request
- [ ] Verify HSTS header is present
- [ ] Run SSL Labs test: `ssllabs.com/ssltest/`
- [ ] Verify backup runs successfully
- [ ] Verify monitoring dashboards show data
- [ ] Create first admin account via `/api/v1/auth/register`
- [ ] Test evidence upload → ingest workflow → timeline flow

---

## References

- [Coolify](https://coolify.io/) — self-hosted PaaS
- [K3s](https://k3s.io/) — lightweight Kubernetes
- [SOPS](https://github.com/getsops/sops) — encrypted secrets in git
- [Caddy](https://caddyserver.com/) — automatic HTTPS
- [Patroni](https://github.com/patroni/patroni) — PostgreSQL HA
- [Temporal self-hosted guide](https://docs.temporal.io/self-hosted-guide)
- [MinIO distributed mode](https://min.io/docs/minio/linux/operations/install-deploy-manage/deploy-minio-multi-node-multi-drive.html)
- [Prometheus + Grafana + Loki](https://grafana.com/oss/)
- [Uptime Kuma](https://github.com/louislam/uptime-kuma)
- [Fail2ban](https://github.com/fail2ban/fail2ban)
