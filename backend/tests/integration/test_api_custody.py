"""integration tests for chain of custody api endpoints."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

import httpx
import pytest

from loom.config import Settings, get_settings
from loom.dependencies import get_db_session
from loom.models.chain_of_custody import ChainOfCustodyEntry
from loom.schemas.custody import (
    CaseCustodyVerificationResult,
    CustodyReportResponse,
    CustodyVerificationResult,
)
from loom.security.auth import create_access_token

_ADMIN_ID = UUID("01912345-6789-7abc-8def-0123456789ab")
_USER_ID = UUID("01912345-6789-7abc-8def-0123456789cd")
_CASE_ID = UUID("01912345-6789-7abc-8def-0123456789ef")
_ASSET_ID = UUID("01912345-6789-7abc-8def-012345678901")
_NOW = datetime(2025, 1, 1, tzinfo=UTC)

_SVC = "loom.api.v1.custody"


class _StubSession:
    async def execute(self, stmt):
        return MagicMock()

    def add(self, obj):
        pass

    async def flush(self):
        pass

    async def commit(self):
        pass

    async def refresh(self, obj):
        pass

    async def delete(self, obj):
        pass


def _create_app(settings: Settings) -> object:
    get_settings.cache_clear()
    with patch("loom.config.get_settings", return_value=settings):
        from loom.main import create_app

        application = create_app()

    async def override_db():
        yield _StubSession()

    application.dependency_overrides[get_db_session] = override_db
    application.state.db_session_factory = None
    return application


@pytest.fixture
def mock_settings():
    return Settings(
        secret_key=("test-secret-key-that-is-long-enough-for-validation"),
        database_url="sqlite+aiosqlite:///",
    )


def _auth_header(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _make_custody_entry() -> MagicMock:
    entry = MagicMock(spec=ChainOfCustodyEntry)
    entry.id = uuid4()
    entry.asset_id = _ASSET_ID
    entry.action = "upload"
    entry.actor_id = _ADMIN_ID
    entry.detail = None
    entry.ip_address = "127.0.0.1"
    entry.timestamp = _NOW
    return entry


async def test_list_custody_entries(
    mock_settings: Settings,
) -> None:
    """viewer can list custody entries for an asset."""
    app = _create_app(mock_settings)
    entry = _make_custody_entry()

    # mock db calls for count + data
    call_count = 0

    class _CustomSession(_StubSession):
        async def execute(self, stmt):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                # count query
                result = MagicMock()
                result.scalar_one.return_value = 1
                return result
            # data query
            result = MagicMock()
            scalars = MagicMock()
            scalars.all.return_value = [entry]
            result.scalars.return_value = scalars
            return result

    async def override_db():
        yield _CustomSession()

    app.dependency_overrides[get_db_session] = override_db

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
    ):
        token = create_access_token(str(_USER_ID), "analyst")
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://testserver",
        ) as ac:
            resp = await ac.get(
                f"/api/v1/cases/{_CASE_ID}/assets/{_ASSET_ID}/custody",
                headers=_auth_header(token),
            )

    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 1
    assert len(data["items"]) == 1
    assert data["items"][0]["action"] == "upload"


async def test_list_custody_forbidden(
    mock_settings: Settings,
) -> None:
    """no case access returns 403."""
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
                f"/api/v1/cases/{_CASE_ID}/assets/{_ASSET_ID}/custody",
                headers=_auth_header(token),
            )

    assert resp.status_code == 403


async def test_verify_asset_custody(
    mock_settings: Settings,
) -> None:
    """verify endpoint returns verification result."""
    app = _create_app(mock_settings)
    verification = CustodyVerificationResult(
        asset_id=_ASSET_ID,
        is_valid=True,
        entries_count=3,
        first_entry=_NOW,
        last_entry=_NOW,
        gaps=[],
        issues=[],
        verified_at=_NOW,
    )

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
            f"{_SVC}.verify_asset_chain",
            new_callable=AsyncMock,
            return_value=verification,
        ),
    ):
        token = create_access_token(str(_USER_ID), "analyst")
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://testserver",
        ) as ac:
            resp = await ac.get(
                f"/api/v1/cases/{_CASE_ID}/assets/{_ASSET_ID}/custody/verify",
                headers=_auth_header(token),
            )

    assert resp.status_code == 200
    data = resp.json()
    assert data["is_valid"] is True
    assert data["entries_count"] == 3


async def test_verify_case_custody(
    mock_settings: Settings,
) -> None:
    """verify all assets in a case."""
    app = _create_app(mock_settings)
    result = CaseCustodyVerificationResult(
        case_id=_CASE_ID,
        total_assets=2,
        valid_assets=1,
        invalid_assets=1,
        results=[],
        verified_at=_NOW,
    )

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
            f"{_SVC}.verify_case_custody",
            new_callable=AsyncMock,
            return_value=result,
        ),
    ):
        token = create_access_token(str(_USER_ID), "analyst")
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://testserver",
        ) as ac:
            resp = await ac.get(
                f"/api/v1/cases/{_CASE_ID}/custody/verify",
                headers=_auth_header(token),
            )

    assert resp.status_code == 200
    data = resp.json()
    assert data["total_assets"] == 2
    assert data["valid_assets"] == 1


async def test_custody_report(
    mock_settings: Settings,
) -> None:
    """get custody report for an asset."""
    app = _create_app(mock_settings)
    verification = CustodyVerificationResult(
        asset_id=_ASSET_ID,
        is_valid=True,
        entries_count=1,
        first_entry=_NOW,
        last_entry=_NOW,
        gaps=[],
        issues=[],
        verified_at=_NOW,
    )
    report = CustodyReportResponse(
        asset_id=_ASSET_ID,
        original_filename="evidence.mp4",
        sha256_hash="abc123",
        sha512_hash="def456",
        file_size_bytes=1024,
        media_type="video",
        uploaded_at=_NOW,
        uploaded_by=_ADMIN_ID,
        chain=[],
        verification=verification,
        generated_at=_NOW,
    )

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
            f"{_SVC}.export_custody_report",
            new_callable=AsyncMock,
            return_value=report,
        ),
    ):
        token = create_access_token(str(_USER_ID), "analyst")
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://testserver",
        ) as ac:
            resp = await ac.get(
                f"/api/v1/cases/{_CASE_ID}/assets/{_ASSET_ID}/custody/report",
                headers=_auth_header(token),
            )

    assert resp.status_code == 200
    data = resp.json()
    assert data["original_filename"] == "evidence.mp4"
    assert data["report_version"] == "1.0"


async def test_custody_report_not_found(
    mock_settings: Settings,
) -> None:
    """report returns 404 when asset not found."""
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
            f"{_SVC}.export_custody_report",
            new_callable=AsyncMock,
            side_effect=ValueError("asset not found"),
        ),
    ):
        token = create_access_token(str(_USER_ID), "analyst")
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://testserver",
        ) as ac:
            resp = await ac.get(
                f"/api/v1/cases/{_CASE_ID}/assets/{_ASSET_ID}/custody/report",
                headers=_auth_header(token),
            )

    assert resp.status_code == 404
