from datetime import UTC, datetime
from unittest.mock import (
    AsyncMock,
    MagicMock,
    patch,
)
from uuid import UUID

import httpx
import pytest_asyncio

from loom.config import Settings, get_settings
from loom.dependencies import get_db_session, get_minio_client
from loom.models.duplicate import (
    DuplicateCluster,
    DuplicateClusterMember,
)
from loom.security.auth import create_access_token

# fixed uuids for test entities
_USER_ID = UUID("01912345-6789-7abc-8def-0123456789cd")
_CASE_ID = UUID("01912345-6789-7abc-8def-0123456789ef")
_CLUSTER_ID = UUID("01912345-6789-7abc-8def-012345678910")
_ASSET_ID_1 = UUID("01912345-6789-7abc-8def-012345678911")
_ASSET_ID_2 = UUID("01912345-6789-7abc-8def-012345678912")
_NOW = datetime(2025, 1, 1, tzinfo=UTC)

# module path prefix for patching
_SVC = "loom.api.v1.duplicates"


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

    async def refresh(self, obj):
        pass

    async def delete(self, obj):
        pass


def _create_app(settings: Settings) -> object:
    """build a test app with stub db and minio."""
    get_settings.cache_clear()

    with patch(
        "loom.config.get_settings",
        return_value=settings,
    ):
        from loom.main import create_app

        application = create_app()

    async def override_db():
        yield _StubSession()

    mock_minio = MagicMock()
    application.dependency_overrides[get_db_session] = override_db
    application.dependency_overrides[get_minio_client] = lambda: mock_minio
    # prevent audit middleware from writing to db
    application.state.db_session_factory = None

    return application


@pytest_asyncio.fixture
def mock_settings() -> Settings:
    """override settings for tests."""
    return Settings(
        secret_key="test-secret-key",
        access_token_expire_minutes=15,
        refresh_token_expire_days=7,
        database_url="sqlite+aiosqlite:///",
    )


def _auth_header(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _make_cluster() -> MagicMock:
    """build a mock cluster."""
    c = MagicMock(spec=DuplicateCluster)
    c.id = _CLUSTER_ID
    c.case_id = _CASE_ID
    c.status = "pending"
    c.created_at = _NOW
    c.updated_at = _NOW
    return c


def _make_member(
    asset_id: UUID,
    is_primary: bool = False,
) -> MagicMock:
    """build a mock cluster member."""
    m = MagicMock(spec=DuplicateClusterMember)
    m.id = UUID("01912345-6789-7abc-8def-012345678920")
    m.cluster_id = _CLUSTER_ID
    m.asset_id = asset_id
    m.phash = "abcdef0123456789"
    m.distance = 0.0
    m.is_primary = is_primary
    m.created_at = _NOW
    return m


async def test_list_duplicates_empty(
    mock_settings: Settings,
) -> None:
    """list duplicates returns empty initially."""
    app = _create_app(mock_settings)

    # mock count returning 0 and empty cluster list
    mock_count_result = MagicMock()
    mock_count_result.scalar_one.return_value = 0

    mock_scalars = MagicMock()
    mock_scalars.all.return_value = []
    mock_select_result = MagicMock()
    mock_select_result.scalars.return_value = mock_scalars

    async def _override_db():
        stub = _StubSession()
        results = [mock_count_result, mock_select_result]
        idx = {"val": 0}

        async def _execute(stmt):
            r = results[idx["val"]]
            idx["val"] += 1
            return r

        stub.execute = _execute  # type: ignore[assignment]
        yield stub

    app.dependency_overrides[get_db_session] = _override_db

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
                f"/api/v1/cases/{_CASE_ID}/duplicates",
                headers=_auth_header(token),
            )

    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 0
    assert data["clusters"] == []


async def test_scan_duplicates(
    mock_settings: Settings,
) -> None:
    """scan duplicates returns 200."""
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
            f"{_SVC}.find_duplicates",
            new_callable=AsyncMock,
            return_value=[],
        ),
    ):
        token = create_access_token(str(_USER_ID), "analyst")
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://testserver",
        ) as ac:
            resp = await ac.post(
                f"/api/v1/cases/{_CASE_ID}/duplicates/scan",
                headers=_auth_header(token),
            )

    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 0
    assert data["clusters"] == []


async def test_update_cluster_status(
    mock_settings: Settings,
) -> None:
    """patch cluster updates status."""
    app = _create_app(mock_settings)
    cluster = _make_cluster()

    # mock: first execute returns cluster, second returns members
    mock_cluster_result = MagicMock()
    mock_cluster_result.scalar_one_or_none.return_value = cluster
    mock_cluster_result.scalar_one.return_value = cluster

    mock_members_result = MagicMock()
    mock_members_result.all.return_value = []

    async def _override_db():
        stub = _StubSession()
        results = [
            mock_cluster_result,  # verify cluster
            mock_cluster_result,  # update_cluster_status
            mock_members_result,  # load members
        ]
        idx = {"val": 0}

        async def _execute(stmt):
            r = results[idx["val"]]
            idx["val"] = min(idx["val"] + 1, len(results) - 1)
            return r

        stub.execute = _execute  # type: ignore[assignment]

        async def _refresh(obj):
            pass

        stub.refresh = _refresh  # type: ignore[assignment]
        yield stub

    app.dependency_overrides[get_db_session] = _override_db

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
            resp = await ac.patch(
                f"/api/v1/cases/{_CASE_ID}/duplicates/{_CLUSTER_ID}",
                json={"status": "reviewed"},
                headers=_auth_header(token),
            )

    assert resp.status_code == 200


async def test_dismiss_cluster(
    mock_settings: Settings,
) -> None:
    """delete cluster dismisses it."""
    app = _create_app(mock_settings)
    cluster = _make_cluster()

    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = cluster

    async def _override_db():
        stub = _StubSession()
        stub.execute = AsyncMock(return_value=mock_result)
        yield stub

    app.dependency_overrides[get_db_session] = _override_db

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
            resp = await ac.delete(
                f"/api/v1/cases/{_CASE_ID}/duplicates/{_CLUSTER_ID}",
                headers=_auth_header(token),
            )

    assert resp.status_code == 204
