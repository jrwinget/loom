from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID

import httpx
import pytest_asyncio

from loom.config import Settings, get_settings
from loom.dependencies import get_db_session
from loom.models.scene import Scene
from loom.security.auth import create_access_token

# fixed uuids for test entities
_ADMIN_ID = UUID("01912345-6789-7abc-8def-0123456789ab")
_CASE_ID = UUID("01912345-6789-7abc-8def-0123456789ef")
_ASSET_ID = UUID("01912345-6789-7abc-8def-012345678903")
_SCENE_ID = UUID("01912345-6789-7abc-8def-012345678904")

_NOW = datetime(2025, 1, 1, tzinfo=UTC)

# module path prefix for patching
_SVC = "loom.api.v1.scenes"


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
        secret_key="test-secret-key",
        access_token_expire_minutes=15,
        refresh_token_expire_days=7,
        database_url="sqlite+aiosqlite:///",
    )


def _auth_header(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _make_scene(
    *,
    scene_id: UUID = _SCENE_ID,
    asset_id: UUID = _ASSET_ID,
    scene_number: int = 1,
    start_time: float = 0.0,
    end_time: float = 5.0,
    duration: float = 5.0,
) -> MagicMock:
    """build a mock scene object."""
    scene = MagicMock(spec=Scene)
    scene.id = scene_id
    scene.asset_id = asset_id
    scene.scene_number = scene_number
    scene.start_time = start_time
    scene.end_time = end_time
    scene.start_frame = 0
    scene.end_frame = 150
    scene.thumbnail_key = None
    scene.duration = duration
    scene.created_at = _NOW
    return scene


async def test_list_scenes_empty(
    mock_settings: Settings,
) -> None:
    """get scenes returns empty for asset with no detections."""
    app = _create_app(mock_settings)

    # mock the db execute to return empty result
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = []

    stub_session = _StubSession()
    stub_session.execute = AsyncMock(  # type: ignore[method-assign]
        return_value=mock_result
    )

    async def override_db():
        yield stub_session

    app.dependency_overrides[get_db_session] = override_db  # type: ignore[union-attr]

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
        token = create_access_token(str(_ADMIN_ID), "admin")
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://testserver",
        ) as ac:
            resp = await ac.get(
                f"/api/v1/cases/{_CASE_ID}/assets/{_ASSET_ID}/scenes",
                headers=_auth_header(token),
            )

    assert resp.status_code == 200
    data = resp.json()
    assert data["scenes"] == []
    assert data["total_scenes"] == 0
    assert data["total_duration"] == 0.0


async def test_start_scene_detection(
    mock_settings: Settings,
) -> None:
    """post detect returns 202 accepted."""
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
    ):
        token = create_access_token(str(_ADMIN_ID), "admin")
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://testserver",
        ) as ac:
            resp = await ac.post(
                f"/api/v1/cases/{_CASE_ID}/assets/{_ASSET_ID}/scenes/detect",
                headers=_auth_header(token),
            )

    assert resp.status_code == 202
    data = resp.json()
    assert data["status"] == "accepted"
    assert data["asset_id"] == str(_ASSET_ID)


async def test_list_scenes_ordered(
    mock_settings: Settings,
) -> None:
    """scene list is ordered by scene_number."""
    app = _create_app(mock_settings)

    scene1 = _make_scene(scene_number=1, start_time=0.0)
    scene2 = _make_scene(
        scene_id=UUID("01912345-6789-7abc-8def-012345678905"),
        scene_number=2,
        start_time=5.0,
        end_time=10.0,
    )

    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = [
        scene1,
        scene2,
    ]

    stub_session = _StubSession()
    stub_session.execute = AsyncMock(  # type: ignore[method-assign]
        return_value=mock_result
    )

    async def override_db():
        yield stub_session

    app.dependency_overrides[get_db_session] = override_db  # type: ignore[union-attr]

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
        token = create_access_token(str(_ADMIN_ID), "admin")
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://testserver",
        ) as ac:
            resp = await ac.get(
                f"/api/v1/cases/{_CASE_ID}/assets/{_ASSET_ID}/scenes",
                headers=_auth_header(token),
            )

    assert resp.status_code == 200
    data = resp.json()
    assert data["total_scenes"] == 2
    scenes = data["scenes"]
    assert scenes[0]["scene_number"] == 1
    assert scenes[1]["scene_number"] == 2
