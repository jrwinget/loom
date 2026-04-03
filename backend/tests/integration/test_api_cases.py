from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID

import httpx
import pytest_asyncio

from loom.config import Settings, get_settings
from loom.dependencies import get_db_session
from loom.models.case import Case, CaseMembership
from loom.models.user import User
from loom.security.auth import create_access_token, hash_password

# fixed uuids for test entities
_ADMIN_ID = UUID("01912345-6789-7abc-8def-0123456789ab")
_USER_ID = UUID("01912345-6789-7abc-8def-0123456789cd")
_CASE_ID = UUID("01912345-6789-7abc-8def-0123456789ef")
_MEMBERSHIP_ID = UUID("01912345-6789-7abc-8def-012345678901")

_ADMIN_EMAIL = "admin@example.com"
_USER_EMAIL = "user@example.com"
_USER_PASSWORD = "securepassword123"
_USER_HASH = hash_password(_USER_PASSWORD)
_NOW = datetime(2025, 1, 1, tzinfo=UTC)

# module path prefix for patching service functions
_SVC = "loom.api.v1.cases"


def _make_case(
    *,
    case_id: UUID = _CASE_ID,
    name: str = "Test Case",
    description: str | None = "A test case",
    status: str = "active",
    created_by: UUID = _ADMIN_ID,
) -> MagicMock:
    """build a mock case object."""
    case = MagicMock(spec=Case)
    case.id = case_id
    case.name = name
    case.description = description
    case.status = status
    case.created_by = created_by
    case.created_at = _NOW
    case.updated_at = _NOW
    case.asset_count = 0
    case.event_count = 0
    return case


def _make_membership(
    *,
    membership_id: UUID = _MEMBERSHIP_ID,
    case_id: UUID = _CASE_ID,
    user_id: UUID = _ADMIN_ID,
    role: str = "owner",
    user_email: str = _ADMIN_EMAIL,
) -> MagicMock:
    """build a mock case membership."""
    m = MagicMock(spec=CaseMembership)
    m.id = membership_id
    m.case_id = case_id
    m.user_id = user_id
    m.role = role
    m.granted_by = _ADMIN_ID
    m.granted_at = _NOW
    m.user_email = user_email
    return m


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
        secret_key="test-secret-key-that-is-long-enough-for-validation",
        access_token_expire_minutes=15,
        refresh_token_expire_days=7,
        database_url="sqlite+aiosqlite:///",
    )


def _auth_header(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


async def test_create_case(
    mock_settings: Settings,
) -> None:
    """create a case returns 201 with correct data."""
    app = _create_app(mock_settings)
    case = _make_case()

    with (
        patch(
            "loom.security.auth.get_settings",
            return_value=mock_settings,
        ),
        patch(
            f"{_SVC}.create_case",
            new_callable=AsyncMock,
            return_value=case,
        ),
    ):
        token = create_access_token(str(_ADMIN_ID), "admin")
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://testserver",
        ) as ac:
            resp = await ac.post(
                "/api/v1/cases",
                json={
                    "name": "Test Case",
                    "description": "A test case",
                },
                headers=_auth_header(token),
            )

    assert resp.status_code == 201
    data = resp.json()
    assert data["name"] == "Test Case"
    assert data["description"] == "A test case"
    assert data["status"] == "active"
    assert data["asset_count"] == 0
    assert data["event_count"] == 0


async def test_list_cases(
    mock_settings: Settings,
) -> None:
    """list cases returns only cases user is member of."""
    app = _create_app(mock_settings)
    case = _make_case()

    with (
        patch(
            "loom.security.auth.get_settings",
            return_value=mock_settings,
        ),
        patch(
            f"{_SVC}.list_cases",
            new_callable=AsyncMock,
            return_value=([case], 1),
        ),
    ):
        token = create_access_token(str(_ADMIN_ID), "admin")
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://testserver",
        ) as ac:
            resp = await ac.get(
                "/api/v1/cases",
                headers=_auth_header(token),
            )

    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 1
    assert len(data["items"]) == 1
    assert data["items"][0]["name"] == "Test Case"


async def test_get_case_by_id(
    mock_settings: Settings,
) -> None:
    """get case by id works for members."""
    app = _create_app(mock_settings)
    case = _make_case()

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
            f"{_SVC}.get_case",
            new_callable=AsyncMock,
            return_value=case,
        ),
    ):
        token = create_access_token(str(_ADMIN_ID), "admin")
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://testserver",
        ) as ac:
            resp = await ac.get(
                f"/api/v1/cases/{_CASE_ID}",
                headers=_auth_header(token),
            )

    assert resp.status_code == 200
    data = resp.json()
    assert data["name"] == "Test Case"


async def test_get_case_forbidden_for_non_member(
    mock_settings: Settings,
) -> None:
    """get case returns 403 for non-members (unless admin)."""
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
                f"/api/v1/cases/{_CASE_ID}",
                headers=_auth_header(token),
            )

    assert resp.status_code == 403


async def test_update_case(
    mock_settings: Settings,
) -> None:
    """update case works for editors."""
    app = _create_app(mock_settings)
    case = _make_case(name="Updated Case")

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
            f"{_SVC}.update_case",
            new_callable=AsyncMock,
            return_value=case,
        ),
    ):
        token = create_access_token(str(_ADMIN_ID), "admin")
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://testserver",
        ) as ac:
            resp = await ac.patch(
                f"/api/v1/cases/{_CASE_ID}",
                json={"name": "Updated Case"},
                headers=_auth_header(token),
            )

    assert resp.status_code == 200
    data = resp.json()
    assert data["name"] == "Updated Case"


async def test_add_member(
    mock_settings: Settings,
) -> None:
    """add member works for owners."""
    app = _create_app(mock_settings)
    membership = _make_membership(
        user_id=_USER_ID,
        role="viewer",
        user_email=_USER_EMAIL,
    )
    user = MagicMock(spec=User)
    user.id = _USER_ID
    user.email = _USER_EMAIL

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
            f"{_SVC}.add_member",
            new_callable=AsyncMock,
            return_value=membership,
        ),
    ):
        token = create_access_token(str(_ADMIN_ID), "admin")
        # patch the db.execute call for user email lookup
        app_ref = app

        async def _override_db():
            stub = _StubSession()
            result = MagicMock()
            result.scalar_one.return_value = user
            stub.execute = AsyncMock(return_value=result)
            yield stub

        app_ref.dependency_overrides[get_db_session] = _override_db

        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://testserver",
        ) as ac:
            resp = await ac.post(
                f"/api/v1/cases/{_CASE_ID}/members",
                json={
                    "user_id": str(_USER_ID),
                    "role": "viewer",
                },
                headers=_auth_header(token),
            )

    assert resp.status_code == 201
    data = resp.json()
    assert data["role"] == "viewer"


async def test_remove_member(
    mock_settings: Settings,
) -> None:
    """remove member works for owners."""
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
            f"{_SVC}.remove_member",
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
                f"/api/v1/cases/{_CASE_ID}/members/{_USER_ID}",
                headers=_auth_header(token),
            )

    assert resp.status_code == 204


async def test_list_members(
    mock_settings: Settings,
) -> None:
    """list members returns correct data."""
    app = _create_app(mock_settings)
    membership = _make_membership()

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
            f"{_SVC}.list_members",
            new_callable=AsyncMock,
            return_value=[membership],
        ),
    ):
        token = create_access_token(str(_ADMIN_ID), "admin")
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://testserver",
        ) as ac:
            resp = await ac.get(
                f"/api/v1/cases/{_CASE_ID}/members",
                headers=_auth_header(token),
            )

    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["role"] == "owner"
    assert data[0]["user_email"] == _ADMIN_EMAIL
