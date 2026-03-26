from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID

import httpx
import pytest_asyncio

from loom.config import Settings, get_settings
from loom.dependencies import get_db_session
from loom.models.export_bundle import ExportBundle
from loom.security.auth import create_access_token

# fixed uuids for test entities
_ADMIN_ID = UUID("01912345-6789-7abc-8def-0123456789ab")
_CASE_ID = UUID("01912345-6789-7abc-8def-0123456789ef")
_EXPORT_ID = UUID("01912345-6789-7abc-8def-012345678902")

_NOW = datetime(2025, 1, 1, tzinfo=UTC)

# module path prefix for patching service functions
_SVC = "loom.api.v1.exports"


def _make_export(
    *,
    export_id: UUID = _EXPORT_ID,
    case_id: UUID = _CASE_ID,
    name: str = "Test Export",
    fmt: str = "zip",
    status: str = "pending",
    created_by: UUID = _ADMIN_ID,
) -> MagicMock:
    """build a mock export bundle object."""
    export = MagicMock(spec=ExportBundle)
    export.id = export_id
    export.case_id = case_id
    export.name = name
    export.format = fmt
    export.status = status
    export.storage_key = ""
    export.sha256_hash = ""
    export.manifest = None
    export.created_by = created_by
    export.created_at = _NOW
    return export


class _StubSession:
    """minimal stub session for dependency override."""

    async def execute(self, stmt):
        return MagicMock()

    def add(self, obj):
        pass

    async def flush(self) -> None:
        pass

    async def commit(self) -> None:
        pass

    async def refresh(self, obj) -> None:
        pass

    async def delete(self, obj) -> None:
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
        secret_key="test-secret-key-that-is-long-enough-for-validation",
        access_token_expire_minutes=15,
        refresh_token_expire_days=7,
        database_url="sqlite+aiosqlite:///",
    )


def _auth_header(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


async def test_create_export(
    mock_settings: Settings,
) -> None:
    """create an export returns 201 with correct data."""
    app = _create_app(mock_settings)
    export = _make_export()

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
            f"{_SVC}.create_export_record",
            new_callable=AsyncMock,
            return_value=export,
        ),
    ):
        token = create_access_token(str(_ADMIN_ID), "admin")
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://testserver",
        ) as ac:
            resp = await ac.post(
                f"/api/v1/cases/{_CASE_ID}/exports",
                json={
                    "name": "Test Export",
                    "format": "zip",
                },
                headers=_auth_header(token),
            )

    assert resp.status_code == 201
    data = resp.json()
    assert data["name"] == "Test Export"
    assert data["format"] == "zip"
    assert data["status"] == "pending"


async def test_list_exports(
    mock_settings: Settings,
) -> None:
    """list exports returns paginated results."""
    app = _create_app(mock_settings)
    export = _make_export()

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
            f"{_SVC}.list_exports",
            new_callable=AsyncMock,
            return_value=([export], 1),
        ),
    ):
        token = create_access_token(str(_ADMIN_ID), "admin")
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://testserver",
        ) as ac:
            resp = await ac.get(
                f"/api/v1/cases/{_CASE_ID}/exports",
                headers=_auth_header(token),
            )

    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 1
    assert len(data["items"]) == 1
    assert data["items"][0]["name"] == "Test Export"


async def test_get_export_detail(
    mock_settings: Settings,
) -> None:
    """get export by id works for members."""
    app = _create_app(mock_settings)
    export = _make_export()

    # stub minio client dependency
    from loom.dependencies import get_minio_client

    mock_minio = MagicMock()

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
            f"{_SVC}.get_export",
            new_callable=AsyncMock,
            return_value=export,
        ),
    ):
        app.dependency_overrides[get_minio_client] = lambda: mock_minio
        token = create_access_token(str(_ADMIN_ID), "admin")
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://testserver",
        ) as ac:
            resp = await ac.get(
                f"/api/v1/cases/{_CASE_ID}/exports/{_EXPORT_ID}",
                headers=_auth_header(token),
            )

    assert resp.status_code == 200
    data = resp.json()
    assert data["name"] == "Test Export"
    assert data["status"] == "pending"
