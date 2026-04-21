from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID

import httpx
import pytest_asyncio

from loom.config import Settings, get_settings
from loom.dependencies import get_db_session
from loom.models.conflict import ConflictResolution
from loom.security.auth import create_access_token

# fixed uuids
_ADMIN_ID = UUID("01912345-6789-7abc-8def-0123456789ab")
_USER_ID = UUID("01912345-6789-7abc-8def-0123456789cd")
_CASE_ID = UUID("01912345-6789-7abc-8def-0123456789ef")
_EVENT_ID = UUID("01912345-6789-7abc-8def-012345678910")
_ASSET_ID = UUID("01912345-6789-7abc-8def-012345678903")
_RESOLUTION_ID = UUID("01912345-6789-7abc-8def-012345678920")

_NOW = datetime(2025, 1, 1, tzinfo=UTC)

# module path prefixes for patching
_SVC_CONF = "loom.api.v1.conflicts"
_SVC_CASE = f"{_SVC_CONF}.check_case_access"

# second case for idor tests
_CASE_B_ID = UUID("01912345-6789-7abc-8def-aaaaaaaaaaaa")


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

    async def refresh(self, obj):  # type: ignore[no-untyped-def]
        pass

    async def delete(self, obj):  # type: ignore[no-untyped-def]
        pass


def _make_resolution(
    *,
    resolution_id: UUID = _RESOLUTION_ID,
    event_id: UUID = _EVENT_ID,
    resolution_type: str = "noted",
    notes: str | None = None,
    resolved_by: UUID = _ADMIN_ID,
) -> MagicMock:
    """build a mock conflict resolution."""
    r = MagicMock(spec=ConflictResolution)
    r.id = resolution_id
    r.event_id = event_id
    r.resolution_type = resolution_type
    r.notes = notes
    r.resolved_by = resolved_by
    r.created_at = _NOW
    r.updated_at = _NOW
    return r


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


async def test_list_conflicts_empty(
    mock_settings: Settings,
) -> None:
    """no events with contradictions returns empty list."""
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
        patch(
            f"{_SVC_CONF}.list_case_conflicts",
            new_callable=AsyncMock,
            return_value=([], 0),
        ),
    ):
        token = create_access_token(str(_ADMIN_ID), "admin")
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://testserver",
        ) as ac:
            resp = await ac.get(
                f"/api/v1/cases/{_CASE_ID}/conflicts",
                headers=_auth_header(token),
            )

    assert resp.status_code == 200
    data = resp.json()
    assert data["items"] == []
    assert data["total"] == 0


async def test_get_event_conflicts_detail(
    mock_settings: Settings,
) -> None:
    """event with supports and contradicts returns both."""
    app = _create_app(mock_settings)

    conflict_detail = {
        "event_id": _EVENT_ID,
        "event_title": "Test event",
        "supporting": [
            {
                "id": UUID("01912345-6789-7abc-8def-012345678930"),
                "asset_id": _ASSET_ID,
                "original_filename": "vid.mp4",
                "annotation_id": None,
                "clip_start": None,
                "clip_end": None,
                "relationship": "supports",
                "notes": None,
            }
        ],
        "contradicting": [
            {
                "id": UUID("01912345-6789-7abc-8def-012345678931"),
                "asset_id": _ASSET_ID,
                "original_filename": "vid.mp4",
                "annotation_id": None,
                "clip_start": 10.0,
                "clip_end": 20.0,
                "relationship": "contradicts",
                "notes": "timing mismatch",
            }
        ],
        "resolutions": [],
    }

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
        patch(
            f"{_SVC_CONF}.get_event_conflicts",
            new_callable=AsyncMock,
            return_value=conflict_detail,
        ),
    ):
        token = create_access_token(str(_ADMIN_ID), "admin")
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://testserver",
        ) as ac:
            resp = await ac.get(
                f"/api/v1/cases/{_CASE_ID}/events/{_EVENT_ID}/conflicts",
                headers=_auth_header(token),
            )

    assert resp.status_code == 200
    data = resp.json()
    assert len(data["supporting"]) == 1
    assert len(data["contradicting"]) == 1
    assert data["supporting"][0]["relationship"] == "supports"
    assert data["contradicting"][0]["relationship"] == "contradicts"


async def test_create_resolution(
    mock_settings: Settings,
) -> None:
    """create resolution returns 201."""
    app = _create_app(mock_settings)
    resolution = _make_resolution(notes="reviewed footage")

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
        patch(
            f"{_SVC_CONF}.create_resolution",
            new_callable=AsyncMock,
            return_value=resolution,
        ),
    ):
        token = create_access_token(str(_ADMIN_ID), "admin")
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://testserver",
        ) as ac:
            resp = await ac.post(
                f"/api/v1/cases/{_CASE_ID}"
                f"/events/{_EVENT_ID}/conflicts/resolve",
                json={
                    "resolution_type": "noted",
                    "notes": "reviewed footage",
                },
                headers=_auth_header(token),
            )

    assert resp.status_code == 201
    data = resp.json()
    assert data["resolution_type"] == "noted"
    assert data["notes"] == "reviewed footage"


async def test_update_resolution(
    mock_settings: Settings,
) -> None:
    """update resolution works."""
    app = _create_app(mock_settings)
    resolution = _make_resolution(
        resolution_type="dismissed",
        notes="updated note",
    )

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
        patch(
            f"{_SVC_CONF}.update_resolution",
            new_callable=AsyncMock,
            return_value=resolution,
        ),
    ):
        token = create_access_token(str(_ADMIN_ID), "admin")
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://testserver",
        ) as ac:
            resp = await ac.patch(
                f"/api/v1/cases/{_CASE_ID}"
                f"/conflicts/resolutions/{_RESOLUTION_ID}",
                json={
                    "resolution_type": "dismissed",
                    "notes": "updated note",
                },
                headers=_auth_header(token),
            )

    assert resp.status_code == 200
    data = resp.json()
    assert data["resolution_type"] == "dismissed"
    assert data["notes"] == "updated note"


async def test_viewer_cannot_create_resolution(
    mock_settings: Settings,
) -> None:
    """viewer cannot create resolution (403)."""
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
                f"/api/v1/cases/{_CASE_ID}"
                f"/events/{_EVENT_ID}/conflicts/resolve",
                json={"resolution_type": "noted"},
                headers=_auth_header(token),
            )

    assert resp.status_code == 403


async def test_cross_case_conflict_access_blocked(
    mock_settings: Settings,
) -> None:
    """cannot access conflicts via wrong case_id (idor)."""
    app = _create_app(mock_settings)

    # return none to simulate event not in case b
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
        patch(
            f"{_SVC_CONF}.get_event_conflicts",
            new_callable=AsyncMock,
            return_value=None,
        ),
    ):
        token = create_access_token(str(_ADMIN_ID), "admin")
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://testserver",
        ) as ac:
            resp = await ac.get(
                f"/api/v1/cases/{_CASE_B_ID}/events/{_EVENT_ID}/conflicts",
                headers=_auth_header(token),
            )

    assert resp.status_code == 404
