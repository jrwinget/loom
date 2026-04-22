"""integration tests for integrity verification api endpoints."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID

import httpx
import pytest

from loom.config import Settings, get_settings
from loom.dependencies import get_db_session, get_storage_backend
from loom.schemas.integrity import (
    CaseIntegrityResult,
    IntegrityReportResponse,
    IntegrityResult,
)
from loom.security.auth import create_access_token
from loom.services.integrity import IntegrityError

_ADMIN_ID = UUID("01912345-6789-7abc-8def-0123456789ab")
_USER_ID = UUID("01912345-6789-7abc-8def-0123456789cd")
_CASE_ID = UUID("01912345-6789-7abc-8def-0123456789ef")
_ASSET_ID = UUID("01912345-6789-7abc-8def-012345678901")
_NOW = datetime(2025, 1, 1, tzinfo=UTC)

_SVC = "loom.api.v1.integrity"


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


def _create_app(settings: Settings) -> object:
    get_settings.cache_clear()
    with patch("loom.config.get_settings", return_value=settings):
        from loom.main import create_app

        application = create_app()

    async def override_db():
        yield _StubSession()

    application.dependency_overrides[get_db_session] = override_db
    application.dependency_overrides[get_storage_backend] = lambda: MagicMock()
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


def _make_integrity_result(
    passed: bool = True,
) -> IntegrityResult:
    sha = "a" * 64
    return IntegrityResult(
        asset_id=_ASSET_ID,
        filename="evidence.mp4",
        storage_key="originals/abc.mp4",
        file_size=1024,
        stored_sha256=sha,
        computed_sha256=sha if passed else "b" * 64,
        stored_sha512=sha,
        computed_sha512=sha if passed else "b" * 64,
        sha256_match=passed,
        sha512_match=passed,
        verified_at=_NOW,
    )


async def test_verify_single_asset(
    mock_settings: Settings,
) -> None:
    """verify single asset returns integrity result."""
    app = _create_app(mock_settings)
    result = _make_integrity_result(passed=True)

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
            f"{_SVC}.verify_asset_integrity",
            new_callable=AsyncMock,
            return_value=result,
        ),
    ):
        token = create_access_token(str(_ADMIN_ID), "admin")
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://testserver",
        ) as ac:
            resp = await ac.post(
                f"/api/v1/cases/{_CASE_ID}/assets/{_ASSET_ID}/verify",
                headers=_auth_header(token),
            )

    assert resp.status_code == 200
    data = resp.json()
    assert data["sha256_match"] is True
    assert data["sha512_match"] is True


async def test_verify_asset_not_found(
    mock_settings: Settings,
) -> None:
    """missing asset returns 404."""
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
            f"{_SVC}.verify_asset_integrity",
            new_callable=AsyncMock,
            side_effect=IntegrityError("not found"),
        ),
    ):
        token = create_access_token(str(_ADMIN_ID), "admin")
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://testserver",
        ) as ac:
            resp = await ac.post(
                f"/api/v1/cases/{_CASE_ID}/assets/{_ASSET_ID}/verify",
                headers=_auth_header(token),
            )

    assert resp.status_code == 404


async def test_verify_asset_forbidden(
    mock_settings: Settings,
) -> None:
    """non-editor returns 403."""
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
            resp = await ac.post(
                f"/api/v1/cases/{_CASE_ID}/assets/{_ASSET_ID}/verify",
                headers=_auth_header(token),
            )

    assert resp.status_code == 403


async def test_verify_case_assets(
    mock_settings: Settings,
) -> None:
    """verify all assets in a case."""
    app = _create_app(mock_settings)
    result = CaseIntegrityResult(
        case_id=_CASE_ID,
        total_assets=3,
        verified_count=3,
        passed_count=2,
        failed_count=1,
        results=[],
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
            f"{_SVC}.verify_case_integrity",
            new_callable=AsyncMock,
            return_value=result,
        ),
    ):
        token = create_access_token(str(_ADMIN_ID), "admin")
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://testserver",
        ) as ac:
            resp = await ac.post(
                f"/api/v1/cases/{_CASE_ID}/verify",
                headers=_auth_header(token),
            )

    assert resp.status_code == 200
    data = resp.json()
    assert data["total_assets"] == 3
    assert data["passed_count"] == 2
    assert data["failed_count"] == 1


async def test_integrity_report(
    mock_settings: Settings,
) -> None:
    """get integrity report for an asset."""
    app = _create_app(mock_settings)
    verification = _make_integrity_result(passed=True)
    report = IntegrityReportResponse(
        asset_id=_ASSET_ID,
        case_id=_CASE_ID,
        original_filename="evidence.mp4",
        storage_key="originals/abc.mp4",
        media_type="video",
        mime_type="video/mp4",
        file_size_bytes=1024,
        uploaded_by=_ADMIN_ID,
        uploaded_at=_NOW,
        verification=verification,
        custody_chain=[],
        report_generated_at=_NOW,
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
            f"{_SVC}.generate_integrity_report",
            new_callable=AsyncMock,
            return_value=report,
        ),
    ):
        token = create_access_token(str(_ADMIN_ID), "admin")
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://testserver",
        ) as ac:
            resp = await ac.get(
                f"/api/v1/cases/{_CASE_ID}/assets/{_ASSET_ID}/integrity-report",
                headers=_auth_header(token),
            )

    assert resp.status_code == 200
    data = resp.json()
    assert data["original_filename"] == "evidence.mp4"
    assert data["verification"]["sha256_match"] is True


async def test_integrity_report_not_found(
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
            f"{_SVC}.generate_integrity_report",
            new_callable=AsyncMock,
            side_effect=IntegrityError("not found"),
        ),
    ):
        token = create_access_token(str(_ADMIN_ID), "admin")
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://testserver",
        ) as ac:
            resp = await ac.get(
                f"/api/v1/cases/{_CASE_ID}/assets/{_ASSET_ID}/integrity-report",
                headers=_auth_header(token),
            )

    assert resp.status_code == 404
