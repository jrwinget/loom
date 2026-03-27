from datetime import UTC, datetime
from unittest.mock import MagicMock, patch
from uuid import UUID

import httpx
import pytest_asyncio

from loom.config import Settings, get_settings
from loom.dependencies import get_db_session
from loom.models.user import User
from loom.security.auth import create_access_token, hash_password

_USER_ID = UUID("01912345-6789-7abc-8def-0123456789ab")
_USER_EMAIL = "admin@example.com"
_USER_PASSWORD = "securepassword123"  # noqa: S105
_USER_HASH = hash_password(_USER_PASSWORD)


def _make_user() -> MagicMock:
    user = MagicMock(spec=User)
    user.id = _USER_ID
    user.email = _USER_EMAIL
    user.display_name = "Admin User"
    user.role = "admin"
    user.is_active = True
    user.password_hash = _USER_HASH
    user.created_at = datetime(2025, 1, 1, tzinfo=UTC)
    user.updated_at = datetime(2025, 1, 1, tzinfo=UTC)
    return user


class MockSession:
    """mock async session that tracks revoked tokens."""

    def __init__(self, *, user=None):
        self._user = user
        self._added: list[object] = []

    async def execute(self, stmt):
        stmt_str = str(stmt)
        # for revocation check queries, return None (not revoked)
        if "revoked_tokens" in stmt_str.lower():
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
        pass


@pytest_asyncio.fixture
def mock_settings():
    return Settings(
        secret_key=("test-secret-key-that-is-long-enough-for-validation"),
        access_token_expire_minutes=15,
        refresh_token_expire_days=7,
        database_url="sqlite+aiosqlite:///",
    )


def _create_app(mock_session, settings):
    get_settings.cache_clear()

    with patch("loom.config.get_settings", return_value=settings):
        from loom.main import create_app

        application = create_app()

    async def override_db():
        yield mock_session

    application.dependency_overrides[get_db_session] = override_db
    # set session factory to None to skip audit writes,
    # but this also skips revocation checks in rbac
    application.state.db_session_factory = None

    return application


async def test_logout_returns_204(
    mock_settings: Settings,
) -> None:
    """POST /auth/logout should return 204 on success."""
    user = _make_user()
    session = MockSession(user=user)
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
            resp = await ac.post(
                "/api/v1/auth/logout",
                headers={"Authorization": f"Bearer {token}"},
            )

    assert resp.status_code == 204


async def test_logout_revokes_token(
    mock_settings: Settings,
) -> None:
    """logout should add a revoked token entry."""
    user = _make_user()
    session = MockSession(user=user)
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
            await ac.post(
                "/api/v1/auth/logout",
                headers={"Authorization": f"Bearer {token}"},
            )

    # verify a revoked token was added
    assert len(session._added) == 1
    revoked = session._added[0]
    assert hasattr(revoked, "jti")
    assert hasattr(revoked, "user_id")


async def test_logout_without_auth(
    mock_settings: Settings,
) -> None:
    """logout without auth header returns 401."""
    session = MockSession()
    app = _create_app(session, mock_settings)

    with patch(
        "loom.security.auth.get_settings",
        return_value=mock_settings,
    ):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://testserver",
        ) as ac:
            resp = await ac.post("/api/v1/auth/logout")

    assert resp.status_code == 401
