from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID

import httpx
import pytest_asyncio

from loom.config import Settings, get_settings
from loom.dependencies import get_db_session
from loom.models.organization import SharedEvidenceLink
from loom.security.auth import create_access_token

# fixed uuids for test entities
_ADMIN_ID = UUID("01912345-6789-7abc-8def-0123456789ab")
_USER_ID = UUID("01912345-6789-7abc-8def-0123456789cd")
_CASE_ID = UUID("01912345-6789-7abc-8def-0123456789ef")
_TARGET_CASE_ID = UUID("01912345-6789-7abc-8def-012345678901")
_ASSET_ID = UUID("01912345-6789-7abc-8def-012345678902")
_LINK_ID = UUID("01912345-6789-7abc-8def-012345678903")

_NOW = datetime(2025, 1, 1, tzinfo=UTC)

# module path prefix for patching
_SVC = "loom.api.v1.shared_evidence"


def _make_link(
    *,
    link_id: UUID = _LINK_ID,
    source_case_id: UUID = _CASE_ID,
    target_case_id: UUID = _TARGET_CASE_ID,
    asset_id: UUID = _ASSET_ID,
    shared_by: UUID = _ADMIN_ID,
    access_level: str = "view",
    expires_at: datetime | None = None,
    original_filename: str = "protest_video.mp4",
) -> MagicMock:
    """build a mock shared evidence link."""
    link = MagicMock(spec=SharedEvidenceLink)
    link.id = link_id
    link.source_case_id = source_case_id
    link.target_case_id = target_case_id
    link.asset_id = asset_id
    link.shared_by = shared_by
    link.access_level = access_level
    link.expires_at = expires_at
    link.created_at = _NOW
    link.original_filename = original_filename
    return link


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


def _auth_header(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def test_share_evidence(
    mock_settings: Settings,
) -> None:
    """share evidence returns 201 with link data."""
    app = _create_app(mock_settings)
    link = _make_link()

    with (
        patch(
            "loom.security.auth.get_settings",
            return_value=mock_settings,
        ),
        patch(
            f"{_SVC}.share_evidence",
            new_callable=AsyncMock,
            return_value=link,
        ),
    ):
        token = create_access_token(str(_ADMIN_ID), "admin")
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://testserver",
        ) as ac:
            resp = await ac.post(
                f"/api/v1/cases/{_CASE_ID}/shared-evidence",
                json={
                    "target_case_id": str(_TARGET_CASE_ID),
                    "asset_id": str(_ASSET_ID),
                    "access_level": "view",
                },
                headers=_auth_header(token),
            )

    assert resp.status_code == 201
    data = resp.json()
    assert data["access_level"] == "view"
    assert data["source_case_id"] == str(_CASE_ID)
    assert data["target_case_id"] == str(_TARGET_CASE_ID)


async def test_share_evidence_forbidden(
    mock_settings: Settings,
) -> None:
    """share evidence returns 403 for insufficient access."""
    app = _create_app(mock_settings)

    with (
        patch(
            "loom.security.auth.get_settings",
            return_value=mock_settings,
        ),
        patch(
            f"{_SVC}.share_evidence",
            new_callable=AsyncMock,
            side_effect=PermissionError("insufficient access"),
        ),
    ):
        token = create_access_token(str(_USER_ID), "analyst")
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://testserver",
        ) as ac:
            resp = await ac.post(
                f"/api/v1/cases/{_CASE_ID}/shared-evidence",
                json={
                    "target_case_id": str(_TARGET_CASE_ID),
                    "asset_id": str(_ASSET_ID),
                },
                headers=_auth_header(token),
            )

    assert resp.status_code == 403


async def test_share_evidence_asset_not_found(
    mock_settings: Settings,
) -> None:
    """share evidence returns 404 if asset not in case."""
    app = _create_app(mock_settings)

    with (
        patch(
            "loom.security.auth.get_settings",
            return_value=mock_settings,
        ),
        patch(
            f"{_SVC}.share_evidence",
            new_callable=AsyncMock,
            side_effect=ValueError("asset not found"),
        ),
    ):
        token = create_access_token(str(_ADMIN_ID), "admin")
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://testserver",
        ) as ac:
            resp = await ac.post(
                f"/api/v1/cases/{_CASE_ID}/shared-evidence",
                json={
                    "target_case_id": str(_TARGET_CASE_ID),
                    "asset_id": str(_ASSET_ID),
                },
                headers=_auth_header(token),
            )

    assert resp.status_code == 404


async def test_share_evidence_forbidden_no_target_access(
    mock_settings: Settings,
) -> None:
    """share evidence returns 403 when user has no access to target."""
    app = _create_app(mock_settings)

    with (
        patch(
            "loom.security.auth.get_settings",
            return_value=mock_settings,
        ),
        patch(
            f"{_SVC}.share_evidence",
            new_callable=AsyncMock,
            side_effect=PermissionError("insufficient access on target case"),
        ),
    ):
        token = create_access_token(str(_USER_ID), "analyst")
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://testserver",
        ) as ac:
            resp = await ac.post(
                f"/api/v1/cases/{_CASE_ID}/shared-evidence",
                json={
                    "target_case_id": str(_TARGET_CASE_ID),
                    "asset_id": str(_ASSET_ID),
                },
                headers=_auth_header(token),
            )

    assert resp.status_code == 403
    assert "target case" in resp.json()["detail"]


async def test_share_evidence_forbidden_viewer_on_target(
    mock_settings: Settings,
) -> None:
    """share evidence returns 403 when user is only viewer on target."""
    app = _create_app(mock_settings)

    with (
        patch(
            "loom.security.auth.get_settings",
            return_value=mock_settings,
        ),
        patch(
            f"{_SVC}.share_evidence",
            new_callable=AsyncMock,
            side_effect=PermissionError("insufficient access on target case"),
        ),
    ):
        token = create_access_token(str(_USER_ID), "analyst")
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://testserver",
        ) as ac:
            resp = await ac.post(
                f"/api/v1/cases/{_CASE_ID}/shared-evidence",
                json={
                    "target_case_id": str(_TARGET_CASE_ID),
                    "asset_id": str(_ASSET_ID),
                },
                headers=_auth_header(token),
            )

    assert resp.status_code == 403
    assert "target case" in resp.json()["detail"]


async def test_share_evidence_editor_on_both_cases(
    mock_settings: Settings,
) -> None:
    """share succeeds when user is editor on both source and target."""
    app = _create_app(mock_settings)
    link = _make_link()

    with (
        patch(
            "loom.security.auth.get_settings",
            return_value=mock_settings,
        ),
        patch(
            f"{_SVC}.share_evidence",
            new_callable=AsyncMock,
            return_value=link,
        ),
    ):
        token = create_access_token(str(_ADMIN_ID), "admin")
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://testserver",
        ) as ac:
            resp = await ac.post(
                f"/api/v1/cases/{_CASE_ID}/shared-evidence",
                json={
                    "target_case_id": str(_TARGET_CASE_ID),
                    "asset_id": str(_ASSET_ID),
                    "access_level": "view",
                },
                headers=_auth_header(token),
            )

    assert resp.status_code == 201
    data = resp.json()
    assert data["source_case_id"] == str(_CASE_ID)
    assert data["target_case_id"] == str(_TARGET_CASE_ID)


async def test_list_incoming(
    mock_settings: Settings,
) -> None:
    """list incoming shared evidence returns data."""
    app = _create_app(mock_settings)
    link = _make_link()

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
            f"{_SVC}.list_shared_with_case",
            new_callable=AsyncMock,
            return_value=[link],
        ),
    ):
        token = create_access_token(str(_ADMIN_ID), "admin")
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://testserver",
        ) as ac:
            resp = await ac.get(
                f"/api/v1/cases/{_CASE_ID}/shared-evidence/incoming",
                headers=_auth_header(token),
            )

    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["access_level"] == "view"


async def test_list_incoming_forbidden(
    mock_settings: Settings,
) -> None:
    """list incoming returns 403 for non-members."""
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
                f"/api/v1/cases/{_CASE_ID}/shared-evidence/incoming",
                headers=_auth_header(token),
            )

    assert resp.status_code == 403


async def test_list_outgoing(
    mock_settings: Settings,
) -> None:
    """list outgoing shared evidence returns data."""
    app = _create_app(mock_settings)
    link = _make_link()

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
            f"{_SVC}.list_shared_from_case",
            new_callable=AsyncMock,
            return_value=[link],
        ),
    ):
        token = create_access_token(str(_ADMIN_ID), "admin")
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://testserver",
        ) as ac:
            resp = await ac.get(
                f"/api/v1/cases/{_CASE_ID}/shared-evidence/outgoing",
                headers=_auth_header(token),
            )

    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1


async def test_revoke_share(
    mock_settings: Settings,
) -> None:
    """revoke share returns 204 on success."""
    app = _create_app(mock_settings)

    with (
        patch(
            "loom.security.auth.get_settings",
            return_value=mock_settings,
        ),
        patch(
            f"{_SVC}.revoke_share",
            new_callable=AsyncMock,
            return_value=True,
        ),
    ):
        token = create_access_token(str(_ADMIN_ID), "admin")
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://testserver",
        ) as ac:
            resp = await ac.delete(
                f"/api/v1/cases/{_CASE_ID}/shared-evidence/{_LINK_ID}",
                headers=_auth_header(token),
            )

    assert resp.status_code == 204


async def test_revoke_share_not_found(
    mock_settings: Settings,
) -> None:
    """revoke share returns 404 when link not found."""
    app = _create_app(mock_settings)

    with (
        patch(
            "loom.security.auth.get_settings",
            return_value=mock_settings,
        ),
        patch(
            f"{_SVC}.revoke_share",
            new_callable=AsyncMock,
            return_value=False,
        ),
    ):
        token = create_access_token(str(_ADMIN_ID), "admin")
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://testserver",
        ) as ac:
            resp = await ac.delete(
                f"/api/v1/cases/{_CASE_ID}/shared-evidence/{_LINK_ID}",
                headers=_auth_header(token),
            )

    assert resp.status_code == 404


async def test_revoke_share_forbidden(
    mock_settings: Settings,
) -> None:
    """revoke share returns 403 for insufficient access."""
    app = _create_app(mock_settings)

    with (
        patch(
            "loom.security.auth.get_settings",
            return_value=mock_settings,
        ),
        patch(
            f"{_SVC}.revoke_share",
            new_callable=AsyncMock,
            side_effect=PermissionError("insufficient access"),
        ),
    ):
        token = create_access_token(str(_USER_ID), "analyst")
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://testserver",
        ) as ac:
            resp = await ac.delete(
                f"/api/v1/cases/{_CASE_ID}/shared-evidence/{_LINK_ID}",
                headers=_auth_header(token),
            )

    assert resp.status_code == 403
