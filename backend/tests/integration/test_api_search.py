from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID

import httpx
import pytest_asyncio

from loom.config import Settings, get_settings
from loom.dependencies import get_db_session
from loom.security.auth import create_access_token

_ADMIN_ID = UUID("01912345-6789-7abc-8def-0123456789ab")
_USER_ID = UUID("01912345-6789-7abc-8def-0123456789cd")
_CASE_ID = UUID("01912345-6789-7abc-8def-0123456789ef")

# module path prefixes for patching
_SVC_SEARCH = "loom.api.v1.search"
_SVC_CASE = f"{_SVC_SEARCH}.check_case_access"


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


async def test_search_returns_results_structure(
    mock_settings: Settings,
) -> None:
    """search endpoint returns proper response structure."""
    app = _create_app(mock_settings)

    search_data = {
        "results": [
            {
                "type": "annotation",
                "id": "01912345-6789-7abc-8def-012345678902",
                "text": "test content",
                "asset_id": None,
                "relevance_score": 0.0,
                "metadata": {},
            }
        ],
        "total": 1,
        "facets": {
            "transcripts": 0,
            "ocr": 0,
            "annotations": 1,
            "events": 0,
            "assets": 0,
        },
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
            f"{_SVC_SEARCH}.search_case",
            new_callable=AsyncMock,
            return_value=search_data,
        ),
    ):
        token = create_access_token(str(_ADMIN_ID), "admin")
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://testserver",
        ) as ac:
            resp = await ac.get(
                f"/api/v1/cases/{_CASE_ID}/search",
                params={"q": "test"},
                headers=_auth_header(token),
            )

    assert resp.status_code == 200
    data = resp.json()
    assert "results" in data
    assert "total" in data
    assert "facets" in data
    assert data["total"] == 1
    assert len(data["results"]) == 1
    assert data["results"][0]["type"] == "annotation"


async def test_search_with_type_filter(
    mock_settings: Settings,
) -> None:
    """search with types parameter filters results."""
    app = _create_app(mock_settings)

    search_data = {
        "results": [],
        "total": 0,
        "facets": {
            "transcripts": 0,
            "ocr": 0,
            "annotations": 0,
            "events": 0,
            "assets": 0,
        },
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
            f"{_SVC_SEARCH}.search_case",
            new_callable=AsyncMock,
            return_value=search_data,
        ) as mock_search,
    ):
        token = create_access_token(str(_ADMIN_ID), "admin")
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://testserver",
        ) as ac:
            resp = await ac.get(
                f"/api/v1/cases/{_CASE_ID}/search",
                params={
                    "q": "test",
                    "types": "annotations,transcripts",
                },
                headers=_auth_header(token),
            )

    assert resp.status_code == 200
    # verify type filter was passed
    mock_search.assert_called_once()
    call_args = mock_search.call_args
    assert call_args[0][2] == "test"  # query
    assert call_args[0][3] == ["annotations", "transcripts"]


async def test_search_empty_query_returns_422(
    mock_settings: Settings,
) -> None:
    """empty query string returns 422."""
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
    ):
        token = create_access_token(str(_ADMIN_ID), "admin")
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://testserver",
        ) as ac:
            resp = await ac.get(
                f"/api/v1/cases/{_CASE_ID}/search",
                params={"q": ""},
                headers=_auth_header(token),
            )

    assert resp.status_code == 422


async def test_search_non_member_gets_403(
    mock_settings: Settings,
) -> None:
    """non-member gets 403 on search."""
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
            resp = await ac.get(
                f"/api/v1/cases/{_CASE_ID}/search",
                params={"q": "test"},
                headers=_auth_header(token),
            )

    assert resp.status_code == 403
