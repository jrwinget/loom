import httpx
import pytest
from fastapi import FastAPI

from loom.config import get_settings
from loom.main import create_app


@pytest.fixture
def app() -> FastAPI:
    get_settings.cache_clear()
    return create_app()


@pytest.mark.asyncio
async def test_metrics_endpoint_returns_prometheus_format(
    app: FastAPI,
) -> None:
    """the /metrics endpoint returns text/plain prometheus exposition."""
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        resp = await client.get("/metrics")

    assert resp.status_code == 200
    assert "text/plain" in resp.headers["content-type"]
    body = resp.text
    # prometheus-fastapi-instrumentator exposes these by default
    assert "http_request_duration_seconds" in body
    # our custom metrics should also be present
    assert "loom_active_uploads" in body
    assert "loom_audit_failures_total" in body
    assert "loom_db_pool_size" in body


@pytest.mark.asyncio
async def test_metrics_no_auth_required(app: FastAPI) -> None:
    """/metrics must be accessible without an Authorization header."""
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        resp = await client.get("/metrics")

    assert resp.status_code == 200
