from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest
from fastapi import FastAPI

from loom.main import create_app


@pytest.fixture
def mock_app() -> FastAPI:
    """create app with mocked db and minio on state."""
    application = create_app()

    # mock db session factory
    mock_session = AsyncMock()
    mock_session.execute = AsyncMock()
    mock_session_factory = MagicMock()
    mock_session_ctx = AsyncMock()
    mock_session_ctx.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session_ctx.__aexit__ = AsyncMock(return_value=False)
    mock_session_factory.return_value = mock_session_ctx
    application.state.db_session_factory = mock_session_factory

    # mock minio client
    mock_minio = MagicMock()
    mock_minio.bucket_exists.return_value = True
    application.state.minio_client = mock_minio

    # mock db engine so lifespan dispose doesn't fail
    application.state.db_engine = AsyncMock()

    return application


@pytest.fixture
def mock_app_db_down() -> FastAPI:
    """create app where database is unreachable."""
    application = create_app()

    # mock db session factory that raises
    mock_session = AsyncMock()
    mock_session.execute = AsyncMock(
        side_effect=ConnectionRefusedError("db down")
    )
    mock_session_factory = MagicMock()
    mock_session_ctx = AsyncMock()
    mock_session_ctx.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session_ctx.__aexit__ = AsyncMock(return_value=False)
    mock_session_factory.return_value = mock_session_ctx
    application.state.db_session_factory = mock_session_factory

    # mock minio client
    mock_minio = MagicMock()
    mock_minio.bucket_exists.return_value = True
    application.state.minio_client = mock_minio

    application.state.db_engine = AsyncMock()

    return application


async def test_health_returns_ok(
    mock_app: FastAPI,
) -> None:
    """health endpoint returns 200 with ok status."""
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=mock_app),
        base_url="http://testserver",
    ) as client:
        resp = await client.get("/api/v1/health")

    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert data["services"]["database"] == "ok"
    assert data["services"]["storage"] == "ok"


async def test_health_has_request_id(
    mock_app: FastAPI,
) -> None:
    """health response includes X-Request-Id header."""
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=mock_app),
        base_url="http://testserver",
    ) as client:
        resp = await client.get("/api/v1/health")

    assert "x-request-id" in resp.headers


async def test_health_db_down(
    mock_app_db_down: FastAPI,
) -> None:
    """health endpoint reports database error gracefully."""
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=mock_app_db_down),
        base_url="http://testserver",
    ) as client:
        resp = await client.get("/api/v1/health")

    assert resp.status_code == 200
    data = resp.json()
    assert data["services"]["database"] == "error"
    assert data["services"]["storage"] == "ok"
    assert data["status"] == "error"
