# stage 1: build
FROM python:3.12-slim AS builder

WORKDIR /app

RUN pip install --no-cache-dir uv

COPY pyproject.toml uv.lock README.md ./
COPY src/ src/

RUN uv sync --frozen --no-dev

# stage 2: runtime
FROM python:3.12-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --gid 1000 loom \
    && useradd --uid 1000 --gid loom --shell /bin/bash loom

WORKDIR /app

COPY --from=builder /app/.venv /app/.venv
COPY --from=builder /app/src /app/src

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

USER loom

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD ["curl", "-f", "http://localhost:8000/api/v1/health"]

CMD ["uvicorn", "loom.main:app", \
     "--host", "0.0.0.0", \
     "--port", "8000", \
     "--workers", "4"]
