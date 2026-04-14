from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID

import httpx
import pytest_asyncio

from loom.config import Settings, get_settings
from loom.dependencies import get_db_session
from loom.models.annotation import Annotation
from loom.security.auth import create_access_token

# fixed uuids for test entities
_ADMIN_ID = UUID("01912345-6789-7abc-8def-0123456789ab")
_USER_ID = UUID("01912345-6789-7abc-8def-0123456789cd")
_CASE_ID = UUID("01912345-6789-7abc-8def-0123456789ef")
_ANNOTATION_ID = UUID("01912345-6789-7abc-8def-012345678902")
_ASSET_ID = UUID("01912345-6789-7abc-8def-012345678903")

_ADMIN_EMAIL = "admin@example.com"
_NOW = datetime(2025, 1, 1, tzinfo=UTC)

# module path prefixes for patching
_SVC_ANN = "loom.api.v1.annotations"
_SVC_CASE = f"{_SVC_ANN}.check_case_access"


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


def _make_annotation(
    *,
    annotation_id: UUID = _ANNOTATION_ID,
    case_id: UUID = _CASE_ID,
    asset_id: UUID | None = None,
    annotation_type: str = "observation",
    content: str = "Test annotation",
    created_by: UUID = _ADMIN_ID,
    created_by_email: str = _ADMIN_EMAIL,
) -> MagicMock:
    """build a mock annotation object."""
    ann = MagicMock(spec=Annotation)
    ann.id = annotation_id
    ann.case_id = case_id
    ann.asset_id = asset_id
    ann.type = annotation_type
    ann.content = content
    ann.time_start = None
    ann.time_end = None
    ann.frame_number = None
    ann.spatial_region = None
    ann.created_by = created_by
    ann.created_by_email = created_by_email
    ann.created_at = _NOW
    ann.updated_at = _NOW
    return ann


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


async def test_create_annotation(
    mock_settings: Settings,
) -> None:
    """create annotation returns 201."""
    app = _create_app(mock_settings)
    annotation = _make_annotation()

    # stub db.execute for email lookup
    async def _override_db():
        stub = _StubSession()
        result = MagicMock()
        result.scalar_one.return_value = _ADMIN_EMAIL
        stub.execute = AsyncMock(return_value=result)
        yield stub

    app.dependency_overrides[get_db_session] = _override_db

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
            f"{_SVC_ANN}.create_annotation",
            new_callable=AsyncMock,
            return_value=annotation,
        ),
    ):
        token = create_access_token(str(_ADMIN_ID), "admin")
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://testserver",
        ) as ac:
            resp = await ac.post(
                f"/api/v1/cases/{_CASE_ID}/annotations",
                json={
                    "type": "observation",
                    "content": "Test annotation",
                },
                headers=_auth_header(token),
            )

    assert resp.status_code == 201
    data = resp.json()
    assert data["type"] == "observation"
    assert data["content"] == "Test annotation"
    assert data["created_by_email"] == _ADMIN_EMAIL


async def test_list_annotations_filters(
    mock_settings: Settings,
) -> None:
    """list annotations filters by asset and type."""
    app = _create_app(mock_settings)
    ann1 = _make_annotation(asset_id=_ASSET_ID)

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
            f"{_SVC_ANN}.list_annotations",
            new_callable=AsyncMock,
            return_value=([ann1], 1),
        ) as mock_list,
    ):
        token = create_access_token(str(_ADMIN_ID), "admin")
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://testserver",
        ) as ac:
            resp = await ac.get(
                f"/api/v1/cases/{_CASE_ID}/annotations",
                params={
                    "asset_id": str(_ASSET_ID),
                    "type": "observation",
                },
                headers=_auth_header(token),
            )

    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 1
    assert len(data["items"]) == 1
    # verify filters were passed through
    mock_list.assert_called_once()
    call_args = mock_list.call_args
    assert call_args[0][2] == str(_ASSET_ID)
    assert call_args[0][3] == "observation"


async def test_update_annotation(
    mock_settings: Settings,
) -> None:
    """update annotation works."""
    app = _create_app(mock_settings)
    annotation = _make_annotation(content="Updated content")

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
            f"{_SVC_ANN}.get_annotation",
            new_callable=AsyncMock,
            return_value=annotation,
        ),
        patch(
            f"{_SVC_ANN}.update_annotation",
            new_callable=AsyncMock,
            return_value=annotation,
        ),
    ):
        token = create_access_token(str(_ADMIN_ID), "admin")
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://testserver",
        ) as ac:
            resp = await ac.patch(
                f"/api/v1/cases/{_CASE_ID}/annotations/{_ANNOTATION_ID}",
                json={"content": "Updated content"},
                headers=_auth_header(token),
            )

    assert resp.status_code == 200
    data = resp.json()
    assert data["content"] == "Updated content"


async def test_delete_annotation(
    mock_settings: Settings,
) -> None:
    """delete annotation works."""
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
            f"{_SVC_ANN}.get_annotation",
            new_callable=AsyncMock,
            return_value=_make_annotation(),
        ),
        patch(
            f"{_SVC_ANN}.delete_annotation",
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
                f"/api/v1/cases/{_CASE_ID}/annotations/{_ANNOTATION_ID}",
                headers=_auth_header(token),
            )

    assert resp.status_code == 204


async def test_viewer_cannot_create_annotation(
    mock_settings: Settings,
) -> None:
    """viewer cannot create annotation (403)."""
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
                f"/api/v1/cases/{_CASE_ID}/annotations",
                json={
                    "type": "observation",
                    "content": "Should fail",
                },
                headers=_auth_header(token),
            )

    assert resp.status_code == 403


# second case for idor tests
_CASE_B_ID = UUID("01912345-6789-7abc-8def-aaaaaaaaaaaa")


async def test_cannot_get_annotation_from_another_case(
    mock_settings: Settings,
) -> None:
    """annotation in case a must not be accessible via case b url."""
    app = _create_app(mock_settings)
    # annotation belongs to _CASE_ID (case a)
    annotation = _make_annotation(case_id=_CASE_ID)

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
            f"{_SVC_ANN}.get_annotation",
            new_callable=AsyncMock,
            return_value=annotation,
        ),
    ):
        token = create_access_token(str(_ADMIN_ID), "admin")
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://testserver",
        ) as ac:
            # request annotation via case b url
            resp = await ac.get(
                f"/api/v1/cases/{_CASE_B_ID}/annotations/{_ANNOTATION_ID}",
                headers=_auth_header(token),
            )

    assert resp.status_code == 404


async def test_cannot_update_annotation_from_another_case(
    mock_settings: Settings,
) -> None:
    """annotation in case a must not be updatable via case b."""
    app = _create_app(mock_settings)
    annotation = _make_annotation(case_id=_CASE_ID)

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
            f"{_SVC_ANN}.get_annotation",
            new_callable=AsyncMock,
            return_value=annotation,
        ),
        patch(
            f"{_SVC_ANN}.update_annotation",
            new_callable=AsyncMock,
            return_value=annotation,
        ),
    ):
        token = create_access_token(str(_ADMIN_ID), "admin")
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://testserver",
        ) as ac:
            resp = await ac.patch(
                f"/api/v1/cases/{_CASE_B_ID}/annotations/{_ANNOTATION_ID}",
                json={"content": "Hacked content"},
                headers=_auth_header(token),
            )

    assert resp.status_code == 404


async def test_cannot_delete_annotation_from_another_case(
    mock_settings: Settings,
) -> None:
    """annotation in case a must not be deletable via case b."""
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
            f"{_SVC_ANN}.get_annotation",
            new_callable=AsyncMock,
            return_value=_make_annotation(case_id=_CASE_ID),
        ),
        patch(
            f"{_SVC_ANN}.delete_annotation",
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
                f"/api/v1/cases/{_CASE_B_ID}/annotations/{_ANNOTATION_ID}",
                headers=_auth_header(token),
            )

    assert resp.status_code == 404
