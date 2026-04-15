from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID

import httpx
import pytest_asyncio

from loom.config import Settings, get_settings
from loom.dependencies import get_db_session
from loom.security.auth import create_access_token

_ADMIN_ID = UUID("01912345-6789-7abc-8def-0123456789ab")
_CASE_ID = UUID("01912345-6789-7abc-8def-0123456789ef")
_NOW = datetime(2025, 6, 15, 12, 0, 0, tzinfo=UTC)

_SVC = "loom.api.v1.geo"


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

    async def refresh(self, obj) -> None:  # type: ignore[no-untyped-def]
        pass

    async def delete(self, obj) -> None:  # type: ignore[no-untyped-def]
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


def _auth_header(token: str) -> dict:  # type: ignore[type-arg]
    return {"Authorization": f"Bearer {token}"}


async def test_get_geo_assets_empty(
    mock_settings: Settings,
) -> None:
    """geo assets endpoint returns empty list."""
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
            f"{_SVC}.get_geotagged_assets",
            new_callable=AsyncMock,
            return_value=[],
        ),
    ):
        token = create_access_token(str(_ADMIN_ID), "admin")
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://testserver",
        ) as ac:
            resp = await ac.get(
                f"/api/v1/cases/{_CASE_ID}/geo/assets",
                headers=_auth_header(token),
            )

    assert resp.status_code == 200
    assert resp.json() == []


async def test_get_geo_assets_with_data(
    mock_settings: Settings,
) -> None:
    """geo assets endpoint returns asset data."""
    app = _create_app(mock_settings)

    assets = [
        {
            "id": str(_ADMIN_ID),
            "original_filename": "photo.jpg",
            "media_type": "image",
            "lat": 40.7128,
            "lon": -74.0060,
            "capture_time": _NOW,
        }
    ]

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
            f"{_SVC}.get_geotagged_assets",
            new_callable=AsyncMock,
            return_value=assets,
        ),
    ):
        token = create_access_token(str(_ADMIN_ID), "admin")
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://testserver",
        ) as ac:
            resp = await ac.get(
                f"/api/v1/cases/{_CASE_ID}/geo/assets",
                headers=_auth_header(token),
            )

    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["lat"] == 40.7128
    assert data[0]["original_filename"] == "photo.jpg"


async def test_get_geo_events_empty(
    mock_settings: Settings,
) -> None:
    """geo events endpoint returns empty list."""
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
            f"{_SVC}.get_geotagged_events",
            new_callable=AsyncMock,
            return_value=[],
        ),
    ):
        token = create_access_token(str(_ADMIN_ID), "admin")
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://testserver",
        ) as ac:
            resp = await ac.get(
                f"/api/v1/cases/{_CASE_ID}/geo/events",
                headers=_auth_header(token),
            )

    assert resp.status_code == 200
    assert resp.json() == []


async def test_get_geo_events_with_data(
    mock_settings: Settings,
) -> None:
    """geo events endpoint returns event data."""
    app = _create_app(mock_settings)

    events = [
        {
            "id": str(_ADMIN_ID),
            "title": "Protest",
            "status": "accepted",
            "lat": 40.7128,
            "lon": -74.0060,
            "event_time_start": _NOW,
            "has_contradictions": True,
        }
    ]

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
            f"{_SVC}.get_geotagged_events",
            new_callable=AsyncMock,
            return_value=events,
        ),
    ):
        token = create_access_token(str(_ADMIN_ID), "admin")
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://testserver",
        ) as ac:
            resp = await ac.get(
                f"/api/v1/cases/{_CASE_ID}/geo/events",
                headers=_auth_header(token),
            )

    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["has_contradictions"] is True


async def test_get_geo_events_time_filter(
    mock_settings: Settings,
) -> None:
    """time filter query params are passed through."""
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
            f"{_SVC}.get_geotagged_events",
            new_callable=AsyncMock,
            return_value=[],
        ),
    ):
        token = create_access_token(str(_ADMIN_ID), "admin")
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://testserver",
        ) as ac:
            resp = await ac.get(
                f"/api/v1/cases/{_CASE_ID}/geo/events"
                "?time_start=2025-01-01T00:00:00Z"
                "&time_end=2025-12-31T23:59:59Z",
                headers=_auth_header(token),
            )

    assert resp.status_code == 200


async def test_get_geo_bounds_null(
    mock_settings: Settings,
) -> None:
    """bounds endpoint returns null when no geo data."""
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
            f"{_SVC}.get_geo_bounds",
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
                f"/api/v1/cases/{_CASE_ID}/geo/bounds",
                headers=_auth_header(token),
            )

    assert resp.status_code == 200
    assert resp.json() is None


async def test_get_geo_bounds_with_data(
    mock_settings: Settings,
) -> None:
    """bounds endpoint returns bounding box."""
    app = _create_app(mock_settings)

    bounds = {
        "min_lat": 40.0,
        "max_lat": 41.0,
        "min_lon": -75.0,
        "max_lon": -73.0,
        "time_start": _NOW,
        "time_end": _NOW,
    }

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
            f"{_SVC}.get_geo_bounds",
            new_callable=AsyncMock,
            return_value=bounds,
        ),
    ):
        token = create_access_token(str(_ADMIN_ID), "admin")
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://testserver",
        ) as ac:
            resp = await ac.get(
                f"/api/v1/cases/{_CASE_ID}/geo/bounds",
                headers=_auth_header(token),
            )

    assert resp.status_code == 200
    data = resp.json()
    assert data["min_lat"] == 40.0
    assert data["max_lon"] == -73.0


async def test_geo_requires_auth(
    mock_settings: Settings,
) -> None:
    """geo endpoints require authentication."""
    app = _create_app(mock_settings)

    with patch(
        "loom.security.auth.get_settings",
        return_value=mock_settings,
    ):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://testserver",
        ) as ac:
            resp = await ac.get(
                f"/api/v1/cases/{_CASE_ID}/geo/assets",
            )

    assert resp.status_code == 401
