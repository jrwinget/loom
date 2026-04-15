from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID

import httpx
import pytest_asyncio

from loom.config import Settings, get_settings
from loom.dependencies import get_db_session
from loom.models.timeline import (
    TimelineEvent,
    TimelineEventEvidence,
)
from loom.security.auth import create_access_token

# fixed uuids for test entities
_ADMIN_ID = UUID("01912345-6789-7abc-8def-0123456789ab")
_USER_ID = UUID("01912345-6789-7abc-8def-0123456789cd")
_CASE_ID = UUID("01912345-6789-7abc-8def-0123456789ef")
_EVENT_ID = UUID("01912345-6789-7abc-8def-012345678910")
_LINK_ID = UUID("01912345-6789-7abc-8def-012345678911")
_ASSET_ID = UUID("01912345-6789-7abc-8def-012345678903")

_NOW = datetime(2025, 1, 1, tzinfo=UTC)

# module path prefixes for patching
_SVC_TL = "loom.api.v1.timeline"
_SVC_CASE = f"{_SVC_TL}.check_case_access"


class _StubSession:
    """minimal stub session for dependency override."""

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


def _make_event(
    *,
    event_id: UUID = _EVENT_ID,
    case_id: UUID = _CASE_ID,
    title: str = "Test event",
    status: str = "draft",
    evidence_count: int = 0,
    has_contradictions: bool = False,
) -> MagicMock:
    """build a mock timeline event object."""
    ev = MagicMock(spec=TimelineEvent)
    ev.id = event_id
    ev.case_id = case_id
    ev.title = title
    ev.description = None
    ev.event_time_start = _NOW
    ev.event_time_end = None
    ev.time_precision = "approximate"
    ev.location_description = None
    ev.location_lat = None
    ev.location_lon = None
    ev.location_confidence = "unknown"
    ev.status = status
    ev.created_by = _ADMIN_ID
    ev.created_at = _NOW
    ev.updated_at = _NOW
    ev.evidence_count = evidence_count
    ev.has_contradictions = has_contradictions
    ev.evidence = []
    return ev


def _make_evidence_link(
    *,
    link_id: UUID = _LINK_ID,
    event_id: UUID = _EVENT_ID,
    relationship: str = "supports",
) -> MagicMock:
    """build a mock evidence link."""
    link = MagicMock(spec=TimelineEventEvidence)
    link.id = link_id
    link.event_id = event_id
    link.asset_id = _ASSET_ID
    link.annotation_id = None
    link.derivative_id = None
    link.clip_start = None
    link.clip_end = None
    link.relationship = relationship
    link.notes = None
    link.linked_by = _ADMIN_ID
    link.linked_at = _NOW
    return link


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


async def test_create_event(
    mock_settings: Settings,
) -> None:
    """create event returns 201."""
    app = _create_app(mock_settings)
    event = _make_event()

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
            f"{_SVC_TL}.create_event",
            new_callable=AsyncMock,
            return_value=event,
        ),
    ):
        token = create_access_token(str(_ADMIN_ID), "admin")
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://testserver",
        ) as ac:
            resp = await ac.post(
                f"/api/v1/cases/{_CASE_ID}/events",
                json={
                    "title": "Test event",
                    "event_time_start": ("2025-01-01T00:00:00Z"),
                },
                headers=_auth_header(token),
            )

    assert resp.status_code == 201
    data = resp.json()
    assert data["title"] == "Test event"
    assert data["status"] == "draft"


async def test_list_events(
    mock_settings: Settings,
) -> None:
    """list events returns paginated results."""
    app = _create_app(mock_settings)
    ev1 = _make_event()

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
            f"{_SVC_TL}.list_events",
            new_callable=AsyncMock,
            return_value=([ev1], 1),
        ),
    ):
        token = create_access_token(str(_ADMIN_ID), "admin")
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://testserver",
        ) as ac:
            resp = await ac.get(
                f"/api/v1/cases/{_CASE_ID}/events",
                headers=_auth_header(token),
            )

    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 1
    assert len(data["items"]) == 1


async def test_update_event(
    mock_settings: Settings,
) -> None:
    """update event works."""
    app = _create_app(mock_settings)
    event = _make_event(title="Updated title")

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
            f"{_SVC_TL}.get_event",
            new_callable=AsyncMock,
            return_value=event,
        ),
        patch(
            f"{_SVC_TL}.update_event",
            new_callable=AsyncMock,
            return_value=event,
        ),
    ):
        token = create_access_token(str(_ADMIN_ID), "admin")
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://testserver",
        ) as ac:
            resp = await ac.patch(
                f"/api/v1/cases/{_CASE_ID}/events/{_EVENT_ID}",
                json={"title": "Updated title"},
                headers=_auth_header(token),
            )

    assert resp.status_code == 200
    data = resp.json()
    assert data["title"] == "Updated title"


async def test_link_evidence(
    mock_settings: Settings,
) -> None:
    """link evidence returns 201."""
    app = _create_app(mock_settings)
    event = _make_event()
    link = _make_evidence_link()

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
            f"{_SVC_TL}.get_event",
            new_callable=AsyncMock,
            return_value=event,
        ),
        patch(
            f"{_SVC_TL}.link_evidence",
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
                f"/api/v1/cases/{_CASE_ID}/events/{_EVENT_ID}/evidence",
                json={
                    "asset_id": str(_ASSET_ID),
                    "relationship": "supports",
                },
                headers=_auth_header(token),
            )

    assert resp.status_code == 201
    data = resp.json()
    assert data["relationship"] == "supports"


async def test_unlink_evidence(
    mock_settings: Settings,
) -> None:
    """unlink evidence returns 204."""
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
            f"{_SVC_TL}.get_event",
            new_callable=AsyncMock,
            return_value=_make_event(),
        ),
        patch(
            f"{_SVC_TL}.unlink_evidence",
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
                f"/api/v1/cases/{_CASE_ID}"
                f"/events/{_EVENT_ID}"
                f"/evidence/{_LINK_ID}",
                headers=_auth_header(token),
            )

    assert resp.status_code == 204


async def test_get_timeline(
    mock_settings: Settings,
) -> None:
    """get timeline returns events with evidence."""
    app = _create_app(mock_settings)
    event = _make_event(evidence_count=1)
    link = _make_evidence_link()
    event.evidence = [link]

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
            f"{_SVC_TL}.get_timeline",
            new_callable=AsyncMock,
            return_value=[event],
        ),
    ):
        token = create_access_token(str(_ADMIN_ID), "admin")
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://testserver",
        ) as ac:
            resp = await ac.get(
                f"/api/v1/cases/{_CASE_ID}/timeline",
                headers=_auth_header(token),
            )

    assert resp.status_code == 200
    data = resp.json()
    assert len(data["events"]) == 1
    assert len(data["events"][0]["evidence"]) == 1


async def test_contradiction_flag(
    mock_settings: Settings,
) -> None:
    """event with contradictions has flag set."""
    app = _create_app(mock_settings)
    event = _make_event(
        evidence_count=2,
        has_contradictions=True,
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
            f"{_SVC_TL}.list_events",
            new_callable=AsyncMock,
            return_value=([event], 1),
        ),
    ):
        token = create_access_token(str(_ADMIN_ID), "admin")
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://testserver",
        ) as ac:
            resp = await ac.get(
                f"/api/v1/cases/{_CASE_ID}/events",
                headers=_auth_header(token),
            )

    assert resp.status_code == 200
    data = resp.json()
    assert data["items"][0]["has_contradictions"] is True


async def test_viewer_cannot_create_event(
    mock_settings: Settings,
) -> None:
    """viewer cannot create event (403)."""
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
                f"/api/v1/cases/{_CASE_ID}/events",
                json={
                    "title": "Should fail",
                    "event_time_start": ("2025-01-01T00:00:00Z"),
                },
                headers=_auth_header(token),
            )

    assert resp.status_code == 403


# second case for idor tests
_CASE_B_ID = UUID("01912345-6789-7abc-8def-aaaaaaaaaaaa")


async def test_cannot_get_event_from_another_case(
    mock_settings: Settings,
) -> None:
    """event in case a must not be accessible via case b url."""
    app = _create_app(mock_settings)
    # event belongs to _CASE_ID (case a)
    event = _make_event(case_id=_CASE_ID)

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
            f"{_SVC_TL}.get_event",
            new_callable=AsyncMock,
            return_value=event,
        ),
    ):
        token = create_access_token(str(_ADMIN_ID), "admin")
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://testserver",
        ) as ac:
            resp = await ac.get(
                f"/api/v1/cases/{_CASE_B_ID}/events/{_EVENT_ID}",
                headers=_auth_header(token),
            )

    assert resp.status_code == 404


async def test_cannot_update_event_from_another_case(
    mock_settings: Settings,
) -> None:
    """event in case a must not be updatable via case b."""
    app = _create_app(mock_settings)
    event = _make_event(case_id=_CASE_ID)

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
            f"{_SVC_TL}.get_event",
            new_callable=AsyncMock,
            return_value=event,
        ),
        patch(
            f"{_SVC_TL}.update_event",
            new_callable=AsyncMock,
            return_value=event,
        ),
    ):
        token = create_access_token(str(_ADMIN_ID), "admin")
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://testserver",
        ) as ac:
            resp = await ac.patch(
                f"/api/v1/cases/{_CASE_B_ID}/events/{_EVENT_ID}",
                json={"title": "Hacked title"},
                headers=_auth_header(token),
            )

    assert resp.status_code == 404


async def test_cannot_unlink_evidence_from_another_case(
    mock_settings: Settings,
) -> None:
    """evidence link via case a must not be deletable via case b."""
    app = _create_app(mock_settings)
    # event belongs to case a
    event = _make_event(case_id=_CASE_ID)

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
            f"{_SVC_TL}.get_event",
            new_callable=AsyncMock,
            return_value=event,
        ),
        patch(
            f"{_SVC_TL}.unlink_evidence",
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
                f"/api/v1/cases/{_CASE_B_ID}"
                f"/events/{_EVENT_ID}"
                f"/evidence/{_LINK_ID}",
                headers=_auth_header(token),
            )

    assert resp.status_code == 404
