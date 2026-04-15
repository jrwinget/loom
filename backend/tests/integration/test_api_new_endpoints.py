"""integration tests for new P1 api endpoints.

covers audit, custody, integrity, and workflow status
endpoints to bring coverage above 90%.
"""

from collections.abc import AsyncIterator
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID

import httpx
import pytest_asyncio

from loom.config import Settings, get_settings
from loom.dependencies import get_db_session, get_minio_client
from loom.security.auth import create_access_token

_USER_ID = UUID("01912345-6789-7abc-8def-0123456789ab")
_CASE_ID = UUID("01912345-6789-7abc-8def-0123456789ef")
_ASSET_ID = UUID("01912345-6789-7abc-8def-012345678902")
_NOW = datetime(2025, 1, 1, tzinfo=UTC)


class MockSession:
    """mock async session for route tests."""

    def __init__(self, **kwargs: object):
        self._returns = kwargs

    async def execute(self, stmt):
        stmt_str = str(stmt).lower()
        if "count" in stmt_str:
            r = MagicMock()
            r.scalar_one.return_value = self._returns.get("count", 0)
            return r
        if "revoked" in stmt_str:
            r = MagicMock()
            r.scalar_one_or_none.return_value = None
            return r
        r = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = self._returns.get("rows", [])
        r.scalars.return_value = mock_scalars
        r.scalar_one_or_none.return_value = self._returns.get("one", None)
        r.scalar_one.return_value = self._returns.get("count", 0)
        return r

    def add(self, obj: object) -> None:
        pass

    async def flush(self) -> None:
        pass

    async def commit(self) -> None:
        pass

    async def refresh(self, obj: object) -> None:
        pass

    def begin_nested(self):
        return _SavepointStub()


class _SavepointStub:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *args: object) -> None:
        pass


@pytest_asyncio.fixture
def mock_settings() -> Settings:
    return Settings(
        secret_key=("test-secret-key-that-is-long-enough-for-validation"),
        access_token_expire_minutes=15,
        refresh_token_expire_days=7,
        database_url="sqlite+aiosqlite:///",
    )


def _create_app(
    session: MockSession,
    settings: Settings,
) -> object:
    get_settings.cache_clear()
    with patch("loom.config.get_settings", return_value=settings):
        from loom.main import create_app

        app = create_app()

    async def override_db() -> AsyncIterator[MockSession]:
        yield session

    app.dependency_overrides[get_db_session] = override_db
    app.dependency_overrides[get_minio_client] = lambda: MagicMock()
    app.state.db_session_factory = None
    return app


def _auth(settings: Settings) -> dict[str, str]:
    token = create_access_token(str(_USER_ID), "admin")
    return {"Authorization": f"Bearer {token}"}


# --- audit endpoints ---


async def test_audit_list(
    mock_settings: Settings,
) -> None:
    """GET /audit returns paginated entries."""
    session = MockSession(count=0, rows=[])
    app = _create_app(session, mock_settings)

    with patch(
        "loom.security.auth.get_settings",
        return_value=mock_settings,
    ):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://testserver",
        ) as ac:
            resp = await ac.get(
                "/api/v1/audit",
                headers=_auth(mock_settings),
            )
    assert resp.status_code == 200


async def test_audit_stats(
    mock_settings: Settings,
) -> None:
    """GET /audit/stats returns stats."""
    session = MockSession(count=0, rows=[])
    app = _create_app(session, mock_settings)

    with patch(
        "loom.security.auth.get_settings",
        return_value=mock_settings,
    ):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://testserver",
        ) as ac:
            resp = await ac.get(
                "/api/v1/audit/stats",
                headers=_auth(mock_settings),
            )
    assert resp.status_code == 200


async def test_case_audit(
    mock_settings: Settings,
) -> None:
    """GET /cases/{id}/audit returns case audit entries."""
    session = MockSession(count=0, rows=[])
    app = _create_app(session, mock_settings)

    with (
        patch(
            "loom.security.auth.get_settings",
            return_value=mock_settings,
        ),
        patch(
            "loom.api.v1.audit.check_case_access",
            new_callable=AsyncMock,
            return_value=True,
        ),
    ):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://testserver",
        ) as ac:
            resp = await ac.get(
                f"/api/v1/cases/{_CASE_ID}/audit",
                headers=_auth(mock_settings),
            )
    assert resp.status_code == 200


# --- custody endpoints ---


async def test_custody_list(
    mock_settings: Settings,
) -> None:
    """GET custody entries for an asset."""
    session = MockSession(count=0, rows=[])
    app = _create_app(session, mock_settings)

    with (
        patch(
            "loom.security.auth.get_settings",
            return_value=mock_settings,
        ),
        patch(
            "loom.api.v1.custody.check_case_access",
            new_callable=AsyncMock,
            return_value=True,
        ),
    ):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://testserver",
        ) as ac:
            resp = await ac.get(
                f"/api/v1/cases/{_CASE_ID}/assets/{_ASSET_ID}/custody",
                headers=_auth(mock_settings),
            )
    assert resp.status_code == 200


async def test_custody_verify_asset(
    mock_settings: Settings,
) -> None:
    """GET custody verify for a single asset."""
    session = MockSession(count=0, rows=[])
    app = _create_app(session, mock_settings)

    with (
        patch(
            "loom.security.auth.get_settings",
            return_value=mock_settings,
        ),
        patch(
            "loom.api.v1.custody.check_case_access",
            new_callable=AsyncMock,
            return_value=True,
        ),
        patch(
            "loom.api.v1.custody.verify_asset_chain",
            new_callable=AsyncMock,
            return_value=MagicMock(
                asset_id=_ASSET_ID,
                is_valid=True,
                entries_count=0,
                first_entry=None,
                last_entry=None,
                gaps=[],
                issues=[],
            ),
        ),
    ):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://testserver",
        ) as ac:
            resp = await ac.get(
                f"/api/v1/cases/{_CASE_ID}/assets/{_ASSET_ID}/custody/verify",
                headers=_auth(mock_settings),
            )
    assert resp.status_code == 200


async def test_custody_verify_case(
    mock_settings: Settings,
) -> None:
    """GET custody verify for whole case."""
    session = MockSession(count=0, rows=[])
    app = _create_app(session, mock_settings)

    with (
        patch(
            "loom.security.auth.get_settings",
            return_value=mock_settings,
        ),
        patch(
            "loom.api.v1.custody.check_case_access",
            new_callable=AsyncMock,
            return_value=True,
        ),
        patch(
            "loom.api.v1.custody.verify_case_custody",
            new_callable=AsyncMock,
            return_value=MagicMock(
                case_id=_CASE_ID,
                total_assets=0,
                valid_count=0,
                invalid_count=0,
                results=[],
            ),
        ),
    ):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://testserver",
        ) as ac:
            resp = await ac.get(
                f"/api/v1/cases/{_CASE_ID}/custody/verify",
                headers=_auth(mock_settings),
            )
    assert resp.status_code == 200


async def test_custody_report_requires_auth(
    mock_settings: Settings,
) -> None:
    """GET custody report without auth returns 401."""
    session = MockSession(count=0, rows=[])
    app = _create_app(session, mock_settings)

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    ) as ac:
        resp = await ac.get(
            f"/api/v1/cases/{_CASE_ID}/assets/{_ASSET_ID}/custody/report",
        )
    assert resp.status_code == 401


# --- integrity endpoints ---


async def test_verify_asset_integrity(
    mock_settings: Settings,
) -> None:
    """POST verify single asset."""
    session = MockSession(count=0, rows=[])
    app = _create_app(session, mock_settings)

    with (
        patch(
            "loom.security.auth.get_settings",
            return_value=mock_settings,
        ),
        patch(
            "loom.api.v1.integrity.check_case_access",
            new_callable=AsyncMock,
            return_value=True,
        ),
        patch(
            "loom.api.v1.integrity.verify_asset_integrity",
            new_callable=AsyncMock,
            return_value=MagicMock(
                asset_id=_ASSET_ID,
                filename="test.jpg",
                stored_sha256="a" * 64,
                computed_sha256="a" * 64,
                stored_sha512="b" * 128,
                computed_sha512="b" * 128,
                sha256_match=True,
                sha512_match=True,
                verified_at=_NOW,
                storage_key="key",
                file_size=1024,
            ),
        ),
    ):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://testserver",
        ) as ac:
            resp = await ac.post(
                f"/api/v1/cases/{_CASE_ID}/assets/{_ASSET_ID}/verify",
                headers=_auth(mock_settings),
            )
    assert resp.status_code == 200


async def test_verify_case_integrity(
    mock_settings: Settings,
) -> None:
    """POST verify all assets in case."""
    session = MockSession(count=0, rows=[])
    app = _create_app(session, mock_settings)

    with (
        patch(
            "loom.security.auth.get_settings",
            return_value=mock_settings,
        ),
        patch(
            "loom.api.v1.integrity.check_case_access",
            new_callable=AsyncMock,
            return_value=True,
        ),
        patch(
            "loom.api.v1.integrity.verify_case_integrity",
            new_callable=AsyncMock,
            return_value=MagicMock(
                case_id=_CASE_ID,
                total_assets=0,
                verified_count=0,
                passed_count=0,
                failed_count=0,
                results=[],
            ),
        ),
    ):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://testserver",
        ) as ac:
            resp = await ac.post(
                f"/api/v1/cases/{_CASE_ID}/verify",
                headers=_auth(mock_settings),
            )
    assert resp.status_code == 200


async def test_integrity_report_requires_auth(
    mock_settings: Settings,
) -> None:
    """GET integrity report without auth returns 401."""
    session = MockSession(count=0, rows=[])
    app = _create_app(session, mock_settings)

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    ) as ac:
        resp = await ac.get(
            f"/api/v1/cases/{_CASE_ID}/assets/{_ASSET_ID}/integrity-report",
        )
    assert resp.status_code == 401


# --- workflow status endpoint ---


async def test_workflow_status(
    mock_settings: Settings,
) -> None:
    """GET workflow status."""
    session = MockSession(count=0, rows=[])
    app = _create_app(session, mock_settings)

    with (
        patch(
            "loom.security.auth.get_settings",
            return_value=mock_settings,
        ),
        patch(
            "loom.api.v1.workflows.check_case_access",
            new_callable=AsyncMock,
            return_value=True,
        ),
        patch(
            "temporalio.client.Client.connect",
            new_callable=AsyncMock,
        ) as mock_connect,
    ):
        mock_client = AsyncMock()
        mock_handle = MagicMock()
        mock_status = MagicMock()
        mock_status.name = "RUNNING"
        mock_handle.describe = AsyncMock(
            return_value=MagicMock(
                status=mock_status,
                start_time=_NOW,
                close_time=None,
            )
        )
        mock_client.get_workflow_handle = MagicMock(return_value=mock_handle)
        mock_connect.return_value = mock_client

        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://testserver",
        ) as ac:
            resp = await ac.get(
                f"/api/v1/cases/{_CASE_ID}/workflows/test-wf-id/status",
                headers=_auth(mock_settings),
            )
    assert resp.status_code == 200


async def test_workflow_status_not_found(
    mock_settings: Settings,
) -> None:
    """GET workflow status for non-existent workflow."""
    session = MockSession(count=0, rows=[])
    app = _create_app(session, mock_settings)

    with (
        patch(
            "loom.security.auth.get_settings",
            return_value=mock_settings,
        ),
        patch(
            "loom.api.v1.workflows.check_case_access",
            new_callable=AsyncMock,
            return_value=True,
        ),
        patch(
            "temporalio.client.Client.connect",
            new_callable=AsyncMock,
        ) as mock_connect,
    ):
        mock_connect.side_effect = Exception("not found")

        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://testserver",
        ) as ac:
            resp = await ac.get(
                f"/api/v1/cases/{_CASE_ID}/workflows/missing-wf/status",
                headers=_auth(mock_settings),
            )
    assert resp.status_code in (404, 500)


# --- auth required tests ---


async def test_audit_requires_admin(
    mock_settings: Settings,
) -> None:
    """GET /audit returns 403 for non-admin."""
    session = MockSession(count=0, rows=[])
    app = _create_app(session, mock_settings)

    with patch(
        "loom.security.auth.get_settings",
        return_value=mock_settings,
    ):
        # create token with analyst role (not admin)
        token = create_access_token(str(_USER_ID), "analyst")
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://testserver",
        ) as ac:
            resp = await ac.get(
                "/api/v1/audit",
                headers={"Authorization": f"Bearer {token}"},
            )
    assert resp.status_code == 403
