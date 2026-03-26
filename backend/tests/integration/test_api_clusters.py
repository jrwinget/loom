"""integration tests for cluster api endpoints."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID

import httpx
import pytest_asyncio

from loom.config import Settings, get_settings
from loom.dependencies import get_db_session
from loom.models.event_cluster import (
    EventCluster,
    EventClusterItem,
)
from loom.security.auth import create_access_token

# fixed uuids for test entities
_ADMIN_ID = UUID("01912345-6789-7abc-8def-0123456789ab")
_CASE_ID = UUID("01912345-6789-7abc-8def-0123456789ef")
_CASE_B_ID = UUID("01912345-6789-7abc-8def-aaaaaaaaaaaa")
_CLUSTER_ID = UUID("01912345-6789-7abc-8def-bbbbbbbbbbbb")
_CLUSTER_B_ID = UUID("01912345-6789-7abc-8def-cccccccccccc")
_ITEM_ID = UUID("01912345-6789-7abc-8def-dddddddddddd")
_ASSET_ID = UUID("01912345-6789-7abc-8def-012345678903")
_CONTENT_ID = UUID("01912345-6789-7abc-8def-eeeeeeeeeeee")
_EVENT_ID = UUID("01912345-6789-7abc-8def-ffffffffffff")

_NOW = datetime(2025, 1, 1, tzinfo=UTC)

_SVC = "loom.api.v1.clusters"
_SVC_CASE = f"{_SVC}.check_case_access"


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


def _make_cluster_item(
    *,
    item_id: UUID = _ITEM_ID,
    cluster_id: UUID = _CLUSTER_ID,
    asset_id: UUID = _ASSET_ID,
) -> MagicMock:
    """build a mock cluster item."""
    item = MagicMock(spec=EventClusterItem)
    item.id = item_id
    item.cluster_id = cluster_id
    item.asset_id = asset_id
    item.content_type = "transcript"
    item.content_id = _CONTENT_ID
    item.absolute_time_start = _NOW
    item.absolute_time_end = _NOW
    item.text_preview = "test content"
    item.created_at = _NOW
    return item


def _make_cluster(
    *,
    cluster_id: UUID = _CLUSTER_ID,
    case_id: UUID = _CASE_ID,
    status: str = "proposed",
    event_id: UUID | None = None,
    items: list[MagicMock] | None = None,
) -> MagicMock:
    """build a mock event cluster."""
    cluster = MagicMock(spec=EventCluster)
    cluster.id = cluster_id
    cluster.case_id = case_id
    cluster.status = status
    cluster.proposed_title = "Test cluster"
    cluster.proposed_description = None
    cluster.time_window_start = _NOW
    cluster.time_window_end = _NOW
    cluster.event_id = event_id
    cluster.reviewed_by = None
    cluster.created_at = _NOW
    cluster.updated_at = _NOW
    cluster.items = items or [_make_cluster_item()]
    return cluster


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


async def test_propose_clusters(
    mock_settings: Settings,
) -> None:
    """propose returns list of clusters."""
    app = _create_app(mock_settings)
    cluster = _make_cluster()

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
            f"{_SVC}.propose_clusters",
            new_callable=AsyncMock,
            return_value=[cluster],
        ),
    ):
        token = create_access_token(str(_ADMIN_ID), "admin")
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://testserver",
        ) as ac:
            resp = await ac.post(
                f"/api/v1/cases/{_CASE_ID}/clusters/propose",
                json={"window_seconds": 60},
                headers=_auth_header(token),
            )

    assert resp.status_code == 201
    data = resp.json()
    assert len(data) == 1
    assert data[0]["status"] == "proposed"
    assert len(data[0]["items"]) == 1


async def test_list_clusters_with_status_filter(
    mock_settings: Settings,
) -> None:
    """list clusters supports status filter."""
    app = _create_app(mock_settings)
    cluster = _make_cluster()

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
            f"{_SVC}.list_clusters",
            new_callable=AsyncMock,
            return_value=([cluster], 1),
        ),
    ):
        token = create_access_token(str(_ADMIN_ID), "admin")
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://testserver",
        ) as ac:
            resp = await ac.get(
                f"/api/v1/cases/{_CASE_ID}/clusters",
                params={"status": "proposed"},
                headers=_auth_header(token),
            )

    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 1
    assert len(data["items"]) == 1


async def test_get_cluster_detail(
    mock_settings: Settings,
) -> None:
    """get detail returns items."""
    app = _create_app(mock_settings)
    cluster = _make_cluster()

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
            f"{_SVC}.get_cluster",
            new_callable=AsyncMock,
            return_value=cluster,
        ),
    ):
        token = create_access_token(str(_ADMIN_ID), "admin")
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://testserver",
        ) as ac:
            resp = await ac.get(
                f"/api/v1/cases/{_CASE_ID}/clusters/{_CLUSTER_ID}",
                headers=_auth_header(token),
            )

    assert resp.status_code == 200
    data = resp.json()
    assert len(data["items"]) == 1
    assert data["proposed_title"] == "Test cluster"


async def test_accept_cluster_creates_event(
    mock_settings: Settings,
) -> None:
    """accept sets status and event_id."""
    app = _create_app(mock_settings)
    cluster = _make_cluster(
        status="accepted",
        event_id=_EVENT_ID,
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
            f"{_SVC}.accept_cluster",
            new_callable=AsyncMock,
            return_value=cluster,
        ),
    ):
        token = create_access_token(str(_ADMIN_ID), "admin")
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://testserver",
        ) as ac:
            resp = await ac.post(
                f"/api/v1/cases/{_CASE_ID}/clusters/{_CLUSTER_ID}/accept",
                json={
                    "title": "Accepted event",
                    "description": "desc",
                },
                headers=_auth_header(token),
            )

    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "accepted"
    assert data["event_id"] is not None


async def test_reject_cluster(
    mock_settings: Settings,
) -> None:
    """reject changes status."""
    app = _create_app(mock_settings)
    cluster = _make_cluster(status="rejected")

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
            f"{_SVC}.reject_cluster",
            new_callable=AsyncMock,
            return_value=cluster,
        ),
    ):
        token = create_access_token(str(_ADMIN_ID), "admin")
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://testserver",
        ) as ac:
            resp = await ac.post(
                f"/api/v1/cases/{_CASE_ID}/clusters/{_CLUSTER_ID}/reject",
                headers=_auth_header(token),
            )

    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "rejected"


async def test_merge_clusters(
    mock_settings: Settings,
) -> None:
    """merge combines clusters."""
    app = _create_app(mock_settings)
    merged = _make_cluster(
        items=[
            _make_cluster_item(),
            _make_cluster_item(
                item_id=UUID("01912345-6789-7abc-8def-111111111111"),
            ),
        ],
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
            f"{_SVC}.merge_clusters",
            new_callable=AsyncMock,
            return_value=merged,
        ),
    ):
        token = create_access_token(str(_ADMIN_ID), "admin")
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://testserver",
        ) as ac:
            resp = await ac.post(
                f"/api/v1/cases/{_CASE_ID}/clusters/merge",
                json={
                    "cluster_ids": [
                        str(_CLUSTER_ID),
                        str(_CLUSTER_B_ID),
                    ],
                },
                headers=_auth_header(token),
            )

    assert resp.status_code == 200
    data = resp.json()
    assert len(data["items"]) == 2


async def test_idor_cluster_wrong_case(
    mock_settings: Settings,
) -> None:
    """cannot access cluster from wrong case."""
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
            f"{_SVC}.get_cluster",
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
                f"/api/v1/cases/{_CASE_B_ID}/clusters/{_CLUSTER_ID}",
                headers=_auth_header(token),
            )

    assert resp.status_code == 404
