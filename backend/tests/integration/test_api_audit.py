"""integration tests for audit log api endpoints."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

import httpx
import pytest

from loom.config import Settings, get_settings
from loom.dependencies import get_db_session
from loom.models.audit import AuditLogEntry
from loom.security.auth import create_access_token

_ADMIN_ID = UUID("01912345-6789-7abc-8def-0123456789ab")
_USER_ID = UUID("01912345-6789-7abc-8def-0123456789cd")
_CASE_ID = UUID("01912345-6789-7abc-8def-0123456789ef")
_NOW = datetime(2025, 1, 1, tzinfo=UTC)

_SVC_AUDIT = "loom.api.v1.audit"


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
        secret_key=(
            "test-secret-key-that-is-long-enough-for-validation"
        ),
        database_url="sqlite+aiosqlite:///",
    )


def _auth_header(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _make_audit_entry(
    *,
    action: str = "POST /api/v1/cases",
    resource_type: str = "case",
) -> MagicMock:
    entry = MagicMock(spec=AuditLogEntry)
    entry.id = uuid4()
    entry.actor_id = _ADMIN_ID
    entry.action = action
    entry.resource_type = resource_type
    entry.resource_id = _CASE_ID
    entry.detail = None
    entry.ip_address = "127.0.0.1"
    entry.user_agent = "test-agent"
    entry.timestamp = _NOW
    return entry


async def test_list_audit_entries_admin(
    mock_settings: Settings,
) -> None:
    """admin can list all audit entries."""
    app = _create_app(mock_settings)
    entry = _make_audit_entry()

    with (
        patch(
            "loom.security.auth.get_settings",
            return_value=mock_settings,
        ),
        patch(
            f"{_SVC_AUDIT}.list_audit_entries",
            new_callable=AsyncMock,
            return_value=([entry], 1),
        ),
    ):
        token = create_access_token(str(_ADMIN_ID), "admin")
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://testserver",
        ) as ac:
            resp = await ac.get(
                "/api/v1/audit",
                headers=_auth_header(token),
            )

    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 1
    assert len(data["items"]) == 1
    assert data["items"][0]["action"] == "POST /api/v1/cases"


async def test_list_audit_entries_non_admin_forbidden(
    mock_settings: Settings,
) -> None:
    """non-admin users cannot access global audit log."""
    app = _create_app(mock_settings)

    with patch(
        "loom.security.auth.get_settings",
        return_value=mock_settings,
    ):
        token = create_access_token(str(_USER_ID), "analyst")
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://testserver",
        ) as ac:
            resp = await ac.get(
                "/api/v1/audit",
                headers=_auth_header(token),
            )

    assert resp.status_code == 403


async def test_audit_stats_admin(
    mock_settings: Settings,
) -> None:
    """admin can access audit stats."""
    app = _create_app(mock_settings)
    from loom.schemas.audit import AuditStatsResponse

    stats = AuditStatsResponse(
        total_entries=42,
        by_action=[],
        by_actor=[],
        earliest_entry=_NOW,
        latest_entry=_NOW,
    )

    with (
        patch(
            "loom.security.auth.get_settings",
            return_value=mock_settings,
        ),
        patch(
            f"{_SVC_AUDIT}.get_audit_stats",
            new_callable=AsyncMock,
            return_value=stats,
        ),
    ):
        token = create_access_token(str(_ADMIN_ID), "admin")
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://testserver",
        ) as ac:
            resp = await ac.get(
                "/api/v1/audit/stats",
                headers=_auth_header(token),
            )

    assert resp.status_code == 200
    data = resp.json()
    assert data["total_entries"] == 42


async def test_case_audit_entries_with_access(
    mock_settings: Settings,
) -> None:
    """editor+ can list case-scoped audit entries."""
    app = _create_app(mock_settings)
    entry = _make_audit_entry()

    with (
        patch(
            "loom.security.auth.get_settings",
            return_value=mock_settings,
        ),
        patch(
            f"{_SVC_AUDIT}.check_case_access",
            new_callable=AsyncMock,
            return_value=True,
        ),
        patch(
            f"{_SVC_AUDIT}.list_audit_entries",
            new_callable=AsyncMock,
            return_value=([entry], 1),
        ),
    ):
        token = create_access_token(str(_USER_ID), "analyst")
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://testserver",
        ) as ac:
            resp = await ac.get(
                f"/api/v1/cases/{_CASE_ID}/audit",
                headers=_auth_header(token),
            )

    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 1


async def test_case_audit_entries_forbidden(
    mock_settings: Settings,
) -> None:
    """denied case access returns 403."""
    app = _create_app(mock_settings)

    with (
        patch(
            "loom.security.auth.get_settings",
            return_value=mock_settings,
        ),
        patch(
            f"{_SVC_AUDIT}.check_case_access",
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
                f"/api/v1/cases/{_CASE_ID}/audit",
                headers=_auth_header(token),
            )

    assert resp.status_code == 403


async def test_list_audit_with_filters(
    mock_settings: Settings,
) -> None:
    """filter params are passed through to the service."""
    app = _create_app(mock_settings)
    mock_list = AsyncMock(return_value=([], 0))

    with (
        patch(
            "loom.security.auth.get_settings",
            return_value=mock_settings,
        ),
        patch(
            f"{_SVC_AUDIT}.list_audit_entries",
            mock_list,
        ),
    ):
        token = create_access_token(str(_ADMIN_ID), "admin")
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://testserver",
        ) as ac:
            resp = await ac.get(
                "/api/v1/audit",
                params={
                    "resource_type": "case",
                    "action": "POST",
                    "skip": 5,
                    "limit": 10,
                },
                headers=_auth_header(token),
            )

    assert resp.status_code == 200
    call_kwargs = mock_list.call_args
    assert call_kwargs.kwargs["resource_type"] == "case"
    assert call_kwargs.kwargs["action"] == "POST"
    assert call_kwargs.kwargs["skip"] == 5
    assert call_kwargs.kwargs["limit"] == 10


async def test_unauthenticated_returns_401(
    mock_settings: Settings,
) -> None:
    """missing token returns 401."""
    app = _create_app(mock_settings)

    with patch(
        "loom.security.auth.get_settings",
        return_value=mock_settings,
    ):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://testserver",
        ) as ac:
            resp = await ac.get("/api/v1/audit")

    assert resp.status_code in (401, 403)
