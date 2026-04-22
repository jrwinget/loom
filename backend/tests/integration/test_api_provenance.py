from datetime import UTC, datetime
from unittest.mock import (
    AsyncMock,
    MagicMock,
    patch,
)
from uuid import UUID

import httpx
import pytest_asyncio

from loom.config import Settings, get_settings
from loom.dependencies import get_db_session, get_storage_backend
from loom.security.auth import create_access_token

# fixed uuids for test entities
_USER_ID = UUID("01912345-6789-7abc-8def-0123456789cd")
_CASE_ID = UUID("01912345-6789-7abc-8def-0123456789ef")
_ASSET_ID = UUID("01912345-6789-7abc-8def-012345678902")
_EXPORT_ID = UUID("01912345-6789-7abc-8def-012345678903")
_OTHER_CASE = UUID("01912345-6789-7abc-8def-aaaaaaaaaaaa")
_NOW = datetime(2025, 1, 1, tzinfo=UTC)

_SVC = "loom.api.v1.provenance"


class _StubSession:
    """minimal stub session for dependency override."""

    async def execute(self, stmt: object) -> MagicMock:
        return MagicMock()

    def add(self, obj: object) -> None:
        pass

    async def flush(self) -> None:
        pass

    async def commit(self) -> None:
        pass

    async def refresh(self, obj: object) -> None:
        pass

    async def delete(self, obj: object) -> None:
        pass


def _create_app(settings: Settings) -> object:
    """build a test app with stub db and minio."""
    get_settings.cache_clear()

    with patch(
        "loom.config.get_settings",
        return_value=settings,
    ):
        from loom.main import create_app

        application = create_app()

    async def override_db():
        yield _StubSession()

    mock_storage = MagicMock()
    application.dependency_overrides[get_db_session] = override_db
    application.dependency_overrides[get_storage_backend] = lambda: mock_storage
    # prevent audit middleware from writing to db
    application.state.db_session_factory = None

    return application


@pytest_asyncio.fixture
def mock_settings() -> Settings:
    """override settings for tests."""
    return Settings(
        secret_key=("test-secret-key-that-is-long-enough-for-validation"),
        access_token_expire_minutes=15,
        refresh_token_expire_days=7,
        database_url="sqlite+aiosqlite:///",
    )


def _auth_header(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def test_get_asset_provenance_empty(
    mock_settings: Settings,
) -> None:
    """get asset provenance returns empty list."""
    app = _create_app(mock_settings)

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
            f"{_SVC}.get_asset_provenance",
            new_callable=AsyncMock,
            return_value=[],
        ),
    ):
        token = create_access_token(str(_USER_ID), "analyst")
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://testserver",
        ) as ac:
            resp = await ac.get(
                f"/api/v1/cases/{_CASE_ID}/assets/{_ASSET_ID}/provenance",
                headers=_auth_header(token),
            )

    assert resp.status_code == 200
    data = resp.json()
    assert data["items"] == []
    assert data["total"] == 0


async def test_get_export_provenance_empty(
    mock_settings: Settings,
) -> None:
    """get export provenance returns empty list."""
    app = _create_app(mock_settings)

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
            f"{_SVC}.get_export_provenance",
            new_callable=AsyncMock,
            return_value=[],
        ),
    ):
        token = create_access_token(str(_USER_ID), "analyst")
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://testserver",
        ) as ac:
            resp = await ac.get(
                f"/api/v1/cases/{_CASE_ID}/exports/{_EXPORT_ID}/provenance",
                headers=_auth_header(token),
            )

    assert resp.status_code == 200
    data = resp.json()
    assert data["items"] == []
    assert data["total"] == 0


async def test_embed_returns_501_when_c2pa_not_installed(
    mock_settings: Settings,
) -> None:
    """post embed returns 501 when c2pa-python not installed."""
    app = _create_app(mock_settings)

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
            "loom.services.provenance._c2pa_available",
            return_value=False,
        ),
    ):
        token = create_access_token(str(_USER_ID), "analyst")
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://testserver",
        ) as ac:
            resp = await ac.post(
                f"/api/v1/cases/{_CASE_ID}"
                f"/exports/{_EXPORT_ID}/provenance/embed",
                headers=_auth_header(token),
            )

    assert resp.status_code == 501
    data = resp.json()
    assert "c2pa" in data["detail"].lower()


async def test_idor_asset_provenance_wrong_case(
    mock_settings: Settings,
) -> None:
    """cannot access provenance from wrong case."""
    app = _create_app(mock_settings)

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
            resp = await ac.get(
                f"/api/v1/cases/{_OTHER_CASE}/assets/{_ASSET_ID}/provenance",
                headers=_auth_header(token),
            )

    assert resp.status_code == 403
