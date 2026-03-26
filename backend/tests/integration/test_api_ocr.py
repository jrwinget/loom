from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID

import httpx
import pytest_asyncio

from loom.config import Settings, get_settings
from loom.dependencies import get_db_session
from loom.security.auth import create_access_token

# fixed uuids for test entities
_ADMIN_ID = UUID("01912345-6789-7abc-8def-0123456789ab")
_USER_ID = UUID("01912345-6789-7abc-8def-0123456789cd")
_CASE_ID = UUID("01912345-6789-7abc-8def-0123456789ef")
_ASSET_ID = UUID("01912345-6789-7abc-8def-012345678903")

_NOW = datetime(2025, 1, 1, tzinfo=UTC)

# module path prefixes for patching
_API_OCR = "loom.api.v1.ocr"
_SVC_CASE = f"{_API_OCR}.check_case_access"


class _StubSession:
    """minimal stub session for dependency override."""

    async def execute(self, stmt):
        # return empty result set by default
        result = MagicMock()
        scalars = MagicMock()
        scalars.all.return_value = []
        result.scalars.return_value = scalars
        return result

    def add(self, obj):
        pass

    async def flush(self):
        pass

    async def commit(self):
        pass

    async def refresh(self, obj):
        pass


def _create_app(settings: Settings) -> object:
    """build a test app with stub db session."""
    get_settings.cache_clear()

    with patch(
        "loom.config.get_settings",
        return_value=settings,
    ):
        from loom.main import create_app

        application = create_app()

    async def override_db():
        yield _StubSession()

    application.dependency_overrides[get_db_session] = override_db
    # prevent audit middleware from writing to db
    application.state.db_session_factory = None

    return application


@pytest_asyncio.fixture
def mock_settings():
    """override settings for tests."""
    return Settings(
        secret_key="test-secret-key",
        access_token_expire_minutes=15,
        refresh_token_expire_days=7,
        database_url="sqlite+aiosqlite:///",
    )


def _auth_header(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


async def test_get_ocr_returns_empty(
    mock_settings: Settings,
) -> None:
    """get ocr returns empty for asset with no results."""
    app = _create_app(mock_settings)

    with (
        patch(
            "loom.security.auth.get_settings",
            return_value=mock_settings,
        ),
        patch(
            _SVC_CASE,
            new_callable=AsyncMock,
            return_value=True,
        ),
    ):
        token = create_access_token(str(_ADMIN_ID), "admin")
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://testserver",
        ) as ac:
            resp = await ac.get(
                f"/api/v1/cases/{_CASE_ID}/assets/{_ASSET_ID}/ocr",
                headers=_auth_header(token),
            )

    assert resp.status_code == 200
    data = resp.json()
    assert data["total_regions"] == 0
    assert data["regions"] == []
    assert data["languages_detected"] == []


async def test_post_ocr_run_returns_202(
    mock_settings: Settings,
) -> None:
    """post run returns 202 accepted."""
    app = _create_app(mock_settings)

    with (
        patch(
            "loom.security.auth.get_settings",
            return_value=mock_settings,
        ),
        patch(
            _SVC_CASE,
            new_callable=AsyncMock,
            return_value=True,
        ),
    ):
        token = create_access_token(str(_ADMIN_ID), "admin")
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://testserver",
        ) as ac:
            resp = await ac.post(
                f"/api/v1/cases/{_CASE_ID}/assets/{_ASSET_ID}/ocr/run",
                headers=_auth_header(token),
            )

    assert resp.status_code == 202
    data = resp.json()
    assert data["status"] == "accepted"
    assert data["asset_id"] == str(_ASSET_ID)


async def test_get_ocr_with_text_filter(
    mock_settings: Settings,
) -> None:
    """get ocr with text filter passes through."""
    app = _create_app(mock_settings)

    with (
        patch(
            "loom.security.auth.get_settings",
            return_value=mock_settings,
        ),
        patch(
            _SVC_CASE,
            new_callable=AsyncMock,
            return_value=True,
        ),
    ):
        token = create_access_token(str(_ADMIN_ID), "admin")
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://testserver",
        ) as ac:
            resp = await ac.get(
                f"/api/v1/cases/{_CASE_ID}/assets/{_ASSET_ID}/ocr",
                params={"text": "hello"},
                headers=_auth_header(token),
            )

    assert resp.status_code == 200
    data = resp.json()
    assert data["total_regions"] == 0


async def test_viewer_cannot_start_ocr(
    mock_settings: Settings,
) -> None:
    """viewer cannot start ocr (403)."""
    app = _create_app(mock_settings)

    with (
        patch(
            "loom.security.auth.get_settings",
            return_value=mock_settings,
        ),
        patch(
            _SVC_CASE,
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
                f"/api/v1/cases/{_CASE_ID}/assets/{_ASSET_ID}/ocr/run",
                headers=_auth_header(token),
            )

    assert resp.status_code == 403
