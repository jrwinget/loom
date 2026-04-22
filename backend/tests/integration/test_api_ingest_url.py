"""Integration tests for POST /cases/:id/ingest-url."""

from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID

import httpx
import pytest_asyncio

from loom.config import Settings, get_settings
from loom.dependencies import get_db_session, get_minio_client
from loom.security.auth import create_access_token

_USER_ID = UUID("01912345-6789-7abc-8def-01234567aa01")
_CASE_ID = UUID("01912345-6789-7abc-8def-01234567aa02")
_NOW = datetime(2026, 4, 22, tzinfo=UTC)

_SVC = "loom.api.v1.assets"


class _SavepointStub:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        pass


class _StubSession:
    """Minimal stub session that captures added objects."""

    def __init__(self) -> None:
        self.added: list[Any] = []
        self.committed = False
        self.rolled_back = False

    async def execute(self, stmt):
        return MagicMock()

    def add(self, obj):
        self.added.append(obj)

    async def flush(self) -> None:
        pass

    async def commit(self) -> None:
        self.committed = True

    async def rollback(self) -> None:
        self.rolled_back = True

    async def refresh(self, obj):
        pass

    async def delete(self, obj):
        pass

    def begin_nested(self):
        return _SavepointStub()


def _create_app(settings: Settings, stub: _StubSession):
    get_settings.cache_clear()
    with patch(
        "loom.config.get_settings",
        return_value=settings,
    ):
        from loom.main import create_app

        application = create_app()

    async def override_db():
        yield stub

    mock_minio = MagicMock()
    application.dependency_overrides[get_db_session] = override_db
    application.dependency_overrides[get_minio_client] = lambda: mock_minio
    application.state.db_session_factory = None
    return application


@pytest_asyncio.fixture
def mock_settings() -> Settings:
    return Settings(
        secret_key="test-secret-key-that-is-long-enough-for-validation",
        access_token_expire_minutes=15,
        refresh_token_expire_days=7,
        database_url="sqlite+aiosqlite:///",
    )


def _auth_header(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _patch_workflow_success():
    mock_client = AsyncMock()
    mock_client.start_workflow = AsyncMock()
    mock_connect = AsyncMock(return_value=mock_client)
    return patch(
        "temporalio.client.Client.connect",
        mock_connect,
    )


async def test_ingest_url_happy_path(
    mock_settings: Settings,
) -> None:
    stub = _StubSession()
    app = _create_app(mock_settings, stub)

    with (
        patch(
            "loom.security.auth.get_settings",
            return_value=mock_settings,
        ),
        patch(
            f"{_SVC}.check_case_access",
            new_callable=AsyncMock,
            return_value=True,
        ),
        _patch_workflow_success(),
    ):
        token = create_access_token(str(_USER_ID), "analyst")
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://testserver",
        ) as ac:
            resp = await ac.post(
                f"/api/v1/cases/{_CASE_ID}/assets/ingest-url",
                json={
                    "url": "https://example.com/video.mp4",
                    "submission_note": "street view",
                },
                headers=_auth_header(token),
            )

    assert resp.status_code == 201
    data = resp.json()
    assert data["status"] == "queued"
    assert data["workflow_id"].startswith("url-ingest-")
    assert "asset_id" in data

    # asset row + custody entry were both added in this request
    assert len(stub.added) == 2
    asset = stub.added[0]
    custody = stub.added[1]
    assert asset.source_uri == "https://example.com/video.mp4"
    assert asset.upload_status == "pending"
    assert custody.action == "url_submitted"
    assert custody.detail == {
        "url": "https://example.com/video.mp4",
        "note": "street view",
    }
    assert stub.committed


async def test_ingest_url_unauthorized(
    mock_settings: Settings,
) -> None:
    stub = _StubSession()
    app = _create_app(mock_settings, stub)

    with (
        patch(
            "loom.security.auth.get_settings",
            return_value=mock_settings,
        ),
        patch(
            f"{_SVC}.check_case_access",
            new_callable=AsyncMock,
            return_value=False,
        ),
    ):
        token = create_access_token(str(_USER_ID), "analyst")
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://testserver",
        ) as ac:
            resp = await ac.post(
                f"/api/v1/cases/{_CASE_ID}/assets/ingest-url",
                json={"url": "https://example.com/video.mp4"},
                headers=_auth_header(token),
            )

    assert resp.status_code == 403


async def test_ingest_url_temporal_unreachable(
    mock_settings: Settings,
) -> None:
    stub = _StubSession()
    app = _create_app(mock_settings, stub)

    with (
        patch(
            "loom.security.auth.get_settings",
            return_value=mock_settings,
        ),
        patch(
            f"{_SVC}.check_case_access",
            new_callable=AsyncMock,
            return_value=True,
        ),
        patch(
            "temporalio.client.Client.connect",
            side_effect=ConnectionError("temporal down"),
        ),
    ):
        token = create_access_token(str(_USER_ID), "analyst")
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://testserver",
        ) as ac:
            resp = await ac.post(
                f"/api/v1/cases/{_CASE_ID}/assets/ingest-url",
                json={"url": "https://example.com/video.mp4"},
                headers=_auth_header(token),
            )

    assert resp.status_code == 502
    assert stub.rolled_back


async def test_ingest_url_501_when_extractor_unavailable(
    mock_settings: Settings,
) -> None:
    """When a URL matches yt-dlp and yt-dlp is unavailable, 501."""
    stub = _StubSession()
    app = _create_app(mock_settings, stub)

    with (
        patch(
            "loom.security.auth.get_settings",
            return_value=mock_settings,
        ),
        patch(
            f"{_SVC}.check_case_access",
            new_callable=AsyncMock,
            return_value=True,
        ),
        patch(
            "loom.services.url_ingest.yt_dlp_extractor._AVAILABLE",
            False,
        ),
        patch(
            "loom.services.url_ingest.archive_extractor._AVAILABLE",
            False,
        ),
    ):
        # force the dispatcher to pick the archive extractor even
        # though it's unavailable by using an archive.org URL
        token = create_access_token(str(_USER_ID), "analyst")
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://testserver",
        ) as ac:
            resp = await ac.post(
                f"/api/v1/cases/{_CASE_ID}/assets/ingest-url",
                json={
                    "url": "https://archive.org/details/foo",
                },
                headers=_auth_header(token),
            )

    assert resp.status_code == 501
