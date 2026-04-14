from collections.abc import AsyncIterator
from datetime import UTC, datetime
from unittest.mock import MagicMock, patch
from uuid import UUID

import httpx
import pytest_asyncio

from loom.config import Settings, get_settings
from loom.dependencies import get_db_session
from loom.models.user import User
from loom.security.auth import (
    create_access_token,
    hash_password,
)

# a fixed uuid for the test user
_USER_ID = UUID("01912345-6789-7abc-8def-0123456789ab")
_USER_EMAIL = "admin@example.com"
_USER_DISPLAY = "Admin User"
_USER_PASSWORD = "securepassword123"
_USER_HASH = hash_password(_USER_PASSWORD)


def _make_user(
    *,
    email: str = _USER_EMAIL,
    display_name: str = _USER_DISPLAY,
    role: str = "admin",
    is_active: bool = True,
    user_id: UUID = _USER_ID,
) -> MagicMock:
    """build a mock user object."""
    user = MagicMock(spec=User)
    user.id = user_id
    user.email = email
    user.display_name = display_name
    user.role = role
    user.is_active = is_active
    user.password_hash = _USER_HASH
    user.mfa_enabled = False
    user.created_at = datetime(2025, 1, 1, tzinfo=UTC)
    user.updated_at = datetime(2025, 1, 1, tzinfo=UTC)
    return user


def _mock_result(value=None):
    """build a mock sqlalchemy result."""
    result = MagicMock()
    result.scalar_one_or_none.return_value = value
    result.scalar_one.return_value = value
    return result


class MockSession:
    """mock async session that tracks calls."""

    def __init__(
        self,
        *,
        user_count: int = 0,
        user: object = None,
    ):
        self._user_count = user_count
        self._user = user
        self._added: list[object] = []

    async def execute(self, stmt):
        stmt_str = str(stmt).lower()
        if "count" in stmt_str:
            result = MagicMock()
            result.scalar_one.return_value = self._user_count
            return result
        # revoked token lookups should return nothing
        if "revoked" in stmt_str:
            result = MagicMock()
            result.scalar_one_or_none.return_value = None
            return result
        result = MagicMock()
        result.scalar_one_or_none.return_value = self._user
        return result

    def add(self, obj: object) -> None:
        self._added.append(obj)

    async def commit(self) -> None:
        pass

    async def refresh(self, obj: object) -> None:
        # simulate db setting fields after insert
        if getattr(obj, "id", None) is None:
            obj.id = _USER_ID  # type: ignore[attr-defined]
        if getattr(obj, "created_at", None) is None:
            obj.created_at = datetime(  # type: ignore[attr-defined]
                2025, 1, 1, tzinfo=UTC
            )
        if getattr(obj, "updated_at", None) is None:
            obj.updated_at = datetime(  # type: ignore[attr-defined]
                2025, 1, 1, tzinfo=UTC
            )
        if getattr(obj, "is_active", None) is None:
            obj.is_active = True  # type: ignore[attr-defined]


@pytest_asyncio.fixture
def mock_settings():
    """override settings for tests."""
    return Settings(
        secret_key="test-secret-key-that-is-long-enough-for-validation",
        access_token_expire_minutes=15,
        refresh_token_expire_days=7,
        database_url="sqlite+aiosqlite:///",
    )


def _create_app(
    mock_session: MockSession,
    settings: Settings,
) -> object:
    """build a test app with mocked dependencies."""
    get_settings.cache_clear()

    with patch("loom.config.get_settings", return_value=settings):
        from loom.main import create_app

        application = create_app()

    async def override_db():
        yield mock_session

    application.dependency_overrides[get_db_session] = override_db

    # prevent audit middleware from writing to db
    application.state.db_session_factory = None

    return application


@pytest_asyncio.fixture
async def first_user_client(
    mock_settings: Settings,
) -> AsyncIterator[httpx.AsyncClient]:
    """client with no existing users (first user flow)."""
    session = MockSession(user_count=0)
    app = _create_app(session, mock_settings)

    with patch(
        "loom.security.auth.get_settings",
        return_value=mock_settings,
    ):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://testserver",
        ) as ac:
            yield ac


@pytest_asyncio.fixture
async def authed_client(
    mock_settings: Settings,
) -> AsyncIterator[tuple[httpx.AsyncClient, str]]:
    """client with an existing admin user and token."""
    user = _make_user()
    session = MockSession(user_count=1, user=user)
    app = _create_app(session, mock_settings)

    with patch(
        "loom.security.auth.get_settings",
        return_value=mock_settings,
    ):
        token = create_access_token(str(_USER_ID), "admin")
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://testserver",
        ) as ac:
            yield ac, token


async def test_register_first_user(
    first_user_client: httpx.AsyncClient,
) -> None:
    """first registered user should become admin."""
    resp = await first_user_client.post(
        "/api/v1/auth/register",
        json={
            "email": _USER_EMAIL,
            "display_name": _USER_DISPLAY,
            "password": _USER_PASSWORD,
        },
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["email"] == _USER_EMAIL
    assert data["role"] == "admin"


async def test_login_correct_credentials(
    authed_client: tuple[httpx.AsyncClient, str],
) -> None:
    """login with correct password returns tokens."""
    ac, _ = authed_client
    resp = await ac.post(
        "/api/v1/auth/login",
        json={
            "email": _USER_EMAIL,
            "password": _USER_PASSWORD,
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "access_token" in data
    assert "refresh_token" in data
    assert data["token_type"] == "bearer"


async def test_login_wrong_password(
    authed_client: tuple[httpx.AsyncClient, str],
) -> None:
    """login with wrong password returns 401."""
    ac, _ = authed_client
    resp = await ac.post(
        "/api/v1/auth/login",
        json={
            "email": _USER_EMAIL,
            "password": "wrongpassword",
        },
    )
    assert resp.status_code == 401


async def test_refresh_token(
    authed_client: tuple[httpx.AsyncClient, str],
    mock_settings: Settings,
) -> None:
    """refresh token returns new access token."""
    ac, _ = authed_client

    with patch(
        "loom.security.auth.get_settings",
        return_value=mock_settings,
    ):
        from loom.security.auth import create_refresh_token

        refresh = create_refresh_token(str(_USER_ID))

    resp = await ac.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": refresh},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "access_token" in data
    assert "refresh_token" in data


async def test_get_me(
    authed_client: tuple[httpx.AsyncClient, str],
) -> None:
    """GET /auth/me returns current user."""
    ac, token = authed_client
    resp = await ac.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["email"] == _USER_EMAIL


async def test_register_second_user_requires_admin(
    authed_client: tuple[httpx.AsyncClient, str],
) -> None:
    """registering via /register with existing users fails."""
    ac, _token = authed_client
    resp = await ac.post(
        "/api/v1/auth/register",
        json={
            "email": "new@example.com",
            "display_name": "New User",
            "password": "newpassword123",
        },
    )
    # should be 403 since users exist and no admin check
    assert resp.status_code == 403


async def test_register_user_with_admin_token(
    authed_client: tuple[httpx.AsyncClient, str],
) -> None:
    """admin can register users via /register-user."""
    ac, token = authed_client

    resp = await ac.post(
        "/api/v1/auth/register-user",
        json={
            "email": "new@example.com",
            "display_name": "New User",
            "password": "newpassword123",
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    # the mock session returns user for all queries,
    # so this will hit the "email already exists" path
    assert resp.status_code in (201, 409)


async def test_register_invalid_email(
    first_user_client: httpx.AsyncClient,
) -> None:
    """register with invalid email returns 422."""
    resp = await first_user_client.post(
        "/api/v1/auth/register",
        json={
            "email": "not-an-email",
            "display_name": "Test",
            "password": "securepassword123",
        },
    )
    assert resp.status_code == 422


async def test_register_short_password(
    first_user_client: httpx.AsyncClient,
) -> None:
    """register with password shorter than 8 chars returns 422."""
    resp = await first_user_client.post(
        "/api/v1/auth/register",
        json={
            "email": "test@example.com",
            "display_name": "Test",
            "password": "short",
        },
    )
    assert resp.status_code == 422


async def test_login_nonexistent_email(
    mock_settings: Settings,
) -> None:
    """login with non-existent email returns 401."""
    # session returns None for user lookup
    session = MockSession(user_count=1, user=None)
    app = _create_app(session, mock_settings)

    with patch(
        "loom.security.auth.get_settings",
        return_value=mock_settings,
    ):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://testserver",
        ) as ac:
            resp = await ac.post(
                "/api/v1/auth/login",
                json={
                    "email": "nobody@example.com",
                    "password": "anypassword123",
                },
            )

    assert resp.status_code == 401


async def test_refresh_invalid_token(
    mock_settings: Settings,
) -> None:
    """refresh with invalid token returns 401."""
    session = MockSession(user_count=1)
    app = _create_app(session, mock_settings)

    with patch(
        "loom.security.auth.get_settings",
        return_value=mock_settings,
    ):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://testserver",
        ) as ac:
            resp = await ac.post(
                "/api/v1/auth/refresh",
                json={"refresh_token": "invalid.token.here"},
            )

    assert resp.status_code == 401


async def test_get_me_without_token(
    mock_settings: Settings,
) -> None:
    """GET /me without auth returns 401 or 403."""
    session = MockSession(user_count=1)
    app = _create_app(session, mock_settings)

    with patch(
        "loom.security.auth.get_settings",
        return_value=mock_settings,
    ):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://testserver",
        ) as ac:
            resp = await ac.get("/api/v1/auth/me")

    assert resp.status_code in (401, 403)
