.PHONY: dev test lint up down build deploy clean help

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

clean: ## remove build artifacts and caches
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .pytest_cache -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .mypy_cache -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .ruff_cache -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name node_modules -exec rm -rf {} + 2>/dev/null || true
	rm -rf frontend/dist backend/dist
