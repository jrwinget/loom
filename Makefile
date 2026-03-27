.PHONY: dev test lint up down build deploy clean help backup restore verify-backup

help: ## show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  %-12s %s\n", $$1, $$2}'

up: ## start docker compose services
	docker compose -f docker/docker-compose.yml up -d

down: ## stop docker compose services
	docker compose -f docker/docker-compose.yml down

dev: up ## start all services for local development
	@echo "Starting backend..."
	cd backend && uv run uvicorn loom.main:app --reload --port 8000 &
	@echo "Starting frontend..."
	cd frontend && pnpm dev &
	@wait

test: test-backend test-frontend ## run all tests

test-backend: ## run backend tests
	cd backend && uv run pytest --cov=loom --cov-report=term-missing

test-frontend: ## run frontend tests
	cd frontend && pnpm test

lint: lint-backend lint-frontend ## run all linters

lint-backend: ## lint and type-check backend
	cd backend && uv run ruff check src tests
	cd backend && uv run ruff format --check src tests
	cd backend && uv run mypy src

lint-frontend: ## lint and type-check frontend
	cd frontend && pnpm lint
	cd frontend && pnpm typecheck

format: ## auto-format all code
	cd backend && uv run ruff format src tests
	cd backend && uv run ruff check --fix src tests
	cd frontend && pnpm format

migrate: ## run database migrations
	cd backend && uv run alembic upgrade head

build: ## build docker images
	docker build -t loom-backend:latest backend/
	docker build -t loom-worker:latest -f backend/Dockerfile.worker backend/
	docker build -t loom-frontend:latest frontend/

deploy: build ## build and start full stack with docker compose
	docker compose -f docker/docker-compose.yml --profile app up -d

backup: ## trigger a manual database backup
	docker compose -f docker/docker-compose.yml run --rm \
		-e POSTGRES_USER=$${POSTGRES_USER:-loom} \
		-e POSTGRES_PASSWORD=$${POSTGRES_PASSWORD:-loom_dev} \
		-e POSTGRES_DB=$${POSTGRES_DB:-loom} \
		-e PGHOST=postgres \
		-e MINIO_ENDPOINT=http://minio:9000 \
		-e MINIO_ROOT_USER=$${MINIO_ROOT_USER:-loom_minio} \
		-e MINIO_ROOT_PASSWORD=$${MINIO_ROOT_PASSWORD:-loom_minio_dev} \
		-e MINIO_BACKUP_BUCKET=loom-backups \
		-v $$(pwd)/docker/postgres/backup.sh:/scripts/backup.sh:ro \
		-v loom-backup-data:/backups \
		--entrypoint /bin/sh \
		postgres:16-alpine -c "\
			apk add --no-cache curl > /dev/null 2>&1; \
			curl -sL https://dl.min.io/client/mc/release/linux-amd64/mc -o /usr/local/bin/mc; \
			chmod +x /usr/local/bin/mc; \
			/scripts/backup.sh"

restore: ## restore from latest or specified backup (usage: make restore [FILE=loom-...dump.gz])
	@echo "This will overwrite the current database. Use FILE= to specify a backup."
	docker compose -f docker/docker-compose.yml run --rm \
		-e POSTGRES_USER=$${POSTGRES_USER:-loom} \
		-e POSTGRES_PASSWORD=$${POSTGRES_PASSWORD:-loom_dev} \
		-e POSTGRES_DB=$${POSTGRES_DB:-loom} \
		-e PGHOST=postgres \
		-e MINIO_ENDPOINT=http://minio:9000 \
		-e MINIO_ROOT_USER=$${MINIO_ROOT_USER:-loom_minio} \
		-e MINIO_ROOT_PASSWORD=$${MINIO_ROOT_PASSWORD:-loom_minio_dev} \
		-e MINIO_BACKUP_BUCKET=loom-backups \
		-v $$(pwd)/docker/postgres/restore.sh:/scripts/restore.sh:ro \
		-v loom-backup-data:/backups \
		--entrypoint /bin/sh \
		postgres:16-alpine -c "\
			apk add --no-cache curl > /dev/null 2>&1; \
			curl -sL https://dl.min.io/client/mc/release/linux-amd64/mc -o /usr/local/bin/mc; \
			chmod +x /usr/local/bin/mc; \
			/scripts/restore.sh --confirm $(FILE)"

verify-backup: ## verify the latest backup by restoring to a temp database
	docker compose -f docker/docker-compose.yml run --rm \
		-e POSTGRES_USER=$${POSTGRES_USER:-loom} \
		-e POSTGRES_PASSWORD=$${POSTGRES_PASSWORD:-loom_dev} \
		-e POSTGRES_DB=$${POSTGRES_DB:-loom} \
		-e PGHOST=postgres \
		-e MINIO_ENDPOINT=http://minio:9000 \
		-e MINIO_ROOT_USER=$${MINIO_ROOT_USER:-loom_minio} \
		-e MINIO_ROOT_PASSWORD=$${MINIO_ROOT_PASSWORD:-loom_minio_dev} \
		-e MINIO_BACKUP_BUCKET=loom-backups \
		-v $$(pwd)/docker/postgres/verify-backup.sh:/scripts/verify-backup.sh:ro \
		-v loom-backup-data:/backups \
		--entrypoint /bin/sh \
		postgres:16-alpine -c "\
			apk add --no-cache curl > /dev/null 2>&1; \
			curl -sL https://dl.min.io/client/mc/release/linux-amd64/mc -o /usr/local/bin/mc; \
			chmod +x /usr/local/bin/mc; \
			/scripts/verify-backup.sh"

clean: ## remove build artifacts and caches
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .pytest_cache -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .mypy_cache -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .ruff_cache -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name node_modules -exec rm -rf {} + 2>/dev/null || true
	rm -rf frontend/dist backend/dist
