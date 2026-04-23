from collections.abc import Iterator
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from fastapi import FastAPI

from loom.main import create_app


@pytest.fixture(autouse=True)
def _temporal_probe_ok() -> Iterator[AsyncMock]:
    """default every test to a reachable temporal server."""
    with patch(
        "loom.api.v1.health._probe_temporal",
        new=AsyncMock(return_value="ok"),
    ) as mock:
        yield mock


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
    assert data["services"]["temporal"] == "ok"


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


async def test_health_temporal_down_fails_overall(
    mock_app: FastAPI,
    _temporal_probe_ok: AsyncMock,
) -> None:
    """unreachable temporal flips overall status to error."""
    _temporal_probe_ok.return_value = "error"

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=mock_app),
        base_url="http://testserver",
    ) as client:
        resp = await client.get("/api/v1/health")

    assert resp.status_code == 200
    data = resp.json()
    assert data["services"]["temporal"] == "error"
    assert data["services"]["database"] == "ok"
    assert data["services"]["storage"] == "ok"
    assert data["status"] == "error"


async def test_health_lite_profile_skips_minio(
    mock_app: FastAPI,
) -> None:
    """lite profile reports storage ok without a minio client."""
    from loom.config import Settings, get_settings

    lite_settings = Settings(
        secret_key="test-secret-key-that-is-long-enough-for-validation",
        database_url="sqlite+aiosqlite:///:memory:",
        deployment_profile="lite",
        storage_signing_secret="test-signing-secret",
    )
    mock_app.state.minio_client = None

    get_settings.cache_clear()
    with patch(
        "loom.api.v1.health.get_settings",
        return_value=lite_settings,
    ):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=mock_app),
            base_url="http://testserver",
        ) as client:
            resp = await client.get("/api/v1/health")

    assert resp.status_code == 200
    data = resp.json()
    assert data["services"]["storage"] == "ok"
    assert data["status"] == "ok"
