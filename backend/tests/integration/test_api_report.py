from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID

import httpx
import pytest_asyncio

from loom.config import Settings, get_settings
from loom.dependencies import get_db_session
from loom.models.export_bundle import ExportBundle
from loom.security.auth import create_access_token

_ADMIN_ID = UUID("01912345-6789-7abc-8def-0123456789ab")
_CASE_ID = UUID("01912345-6789-7abc-8def-0123456789ef")
_EXPORT_ID = UUID("01912345-6789-7abc-8def-012345678903")
_NOW = datetime(2025, 1, 1, tzinfo=UTC)

_SVC = "loom.api.v1.exports"


def _make_export(
    *,
    export_id: UUID = _EXPORT_ID,
    case_id: UUID = _CASE_ID,
    name: str = "Evidence Report",
    fmt: str = "pdf_report",
    status: str = "pending",
    created_by: UUID = _ADMIN_ID,
) -> MagicMock:
    """build a mock export bundle for pdf_report."""
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

    async def execute(self, stmt):  # type: ignore[no-untyped-def]
        return MagicMock()

    def add(self, obj):  # type: ignore[no-untyped-def]
        pass

    async def flush(self) -> None:
        pass

    async def commit(self) -> None:
        pass

    async def refresh(self, obj) -> None:  # type: ignore[no-untyped-def]
        pass

    async def delete(self, obj) -> None:  # type: ignore[no-untyped-def]
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

    async def override_db():  # type: ignore[no-untyped-def]
        yield _StubSession()

    application.dependency_overrides[get_db_session] = override_db
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


def _auth_header(token: str) -> dict:  # type: ignore[type-arg]
    return {"Authorization": f"Bearer {token}"}


async def test_create_pdf_report_export(
    mock_settings: Settings,
) -> None:
    """creating export with format=pdf_report returns 201."""
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
                    "name": "Evidence Report",
                    "format": "pdf_report",
                },
                headers=_auth_header(token),
            )

    assert resp.status_code == 201
    data = resp.json()
    assert data["name"] == "Evidence Report"
    assert data["format"] == "pdf_report"
    assert data["status"] == "pending"


async def test_create_json_manifest_export(
    mock_settings: Settings,
) -> None:
    """creating export with format=json_manifest returns 201."""
    app = _create_app(mock_settings)
    export = _make_export(fmt="json_manifest", name="Manifest")

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
                    "name": "Manifest",
                    "format": "json_manifest",
                },
                headers=_auth_header(token),
            )

    assert resp.status_code == 201
    data = resp.json()
    assert data["format"] == "json_manifest"
    assert data["status"] == "pending"
