from datetime import UTC, datetime
from unittest.mock import MagicMock, patch
from uuid import UUID

import httpx
import pytest_asyncio

from loom.config import Settings, get_settings
from loom.dependencies import get_db_session
from loom.security.auth import hash_password

_USER_ID = UUID("01912345-6789-7abc-8def-0123456789ab")
_USER_EMAIL = "admin@example.com"
_USER_PASSWORD = "securepassword123"  # noqa: S105
_USER_HASH = hash_password(_USER_PASSWORD)


def _make_user(
    *,
    email: str = _USER_EMAIL,
    role: str = "admin",
    is_active: bool = True,
) -> MagicMock:
    """build a mock user."""
    from loom.models.user import User

    user = MagicMock(spec=User)
    user.id = _USER_ID
    user.email = email
    user.display_name = "Admin"
    user.role = role
    user.is_active = is_active
    user.password_hash = _USER_HASH
    user.created_at = datetime(2025, 1, 1, tzinfo=UTC)
    user.updated_at = datetime(2025, 1, 1, tzinfo=UTC)
    return user


class MockSession:
    """mock async session."""

    def __init__(self, *, user_count: int = 1, user=None):
        self._user_count = user_count
        self._user = user
        self._added: list[object] = []

    async def execute(self, stmt, params=None):
        stmt_str = str(stmt)
        if "pg_advisory" in stmt_str.lower():
            return MagicMock()
        if "count" in stmt_str.lower():
            result = MagicMock()
            result.scalar_one.return_value = self._user_count
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
    return Settings(
        secret_key=("test-secret-key-that-is-long-enough-for-validation"),
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
    application.state.db_session_factory = None

    return application


async def test_login_rate_limit(
    mock_settings: Settings,
) -> None:
    """login endpoint should return 429 after 5 requests."""
    from loom.security.rate_limit import limiter

    limiter.reset()

    user = _make_user()
    session = MockSession(user_count=1, user=user)
    app = _create_app(session, mock_settings)

    with patch(
        "loom.security.auth.get_settings",
        return_value=mock_settings,
    ):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://testserver",
        ) as ac:
            # send 5 valid login requests (under limit)
            for _ in range(5):
                resp = await ac.post(
                    "/api/v1/auth/login",
                    json={
                        "email": _USER_EMAIL,
                        "password": _USER_PASSWORD,
                    },
                )
                assert resp.status_code == 200

            # 6th request should be rate limited
            resp = await ac.post(
                "/api/v1/auth/login",
                json={
                    "email": _USER_EMAIL,
                    "password": _USER_PASSWORD,
                },
            )
            assert resp.status_code == 429


async def test_register_rate_limit(
    mock_settings: Settings,
) -> None:
    """register endpoint should return 429 after 3 requests."""
    from loom.security.rate_limit import limiter

    limiter.reset()

    # use user_count=0 so first-user flow works
    session = MockSession(user_count=0, user=None)
    app = _create_app(session, mock_settings)

    with patch(
        "loom.security.auth.get_settings",
        return_value=mock_settings,
    ):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://testserver",
        ) as ac:
            for i in range(3):
                resp = await ac.post(
                    "/api/v1/auth/register",
                    json={
                        "email": f"user{i}@example.com",
                        "display_name": f"User {i}",
                        "password": "securepassword123",
                    },
                )
                # 201 for successful registration
                assert resp.status_code == 201

            # 4th request should be rate limited
            resp = await ac.post(
                "/api/v1/auth/register",
                json={
                    "email": "extra@example.com",
                    "display_name": "Extra",
                    "password": "securepassword123",
                },
            )
            assert resp.status_code == 429


async def test_rate_limit_returns_429_body(
    mock_settings: Settings,
) -> None:
    """429 response should include an error message."""
    from loom.security.rate_limit import limiter

    limiter.reset()

    user = _make_user()
    session = MockSession(user_count=1, user=user)
    app = _create_app(session, mock_settings)

    with patch(
        "loom.security.auth.get_settings",
        return_value=mock_settings,
    ):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://testserver",
        ) as ac:
            # exhaust the rate limit
            for _ in range(5):
                await ac.post(
                    "/api/v1/auth/login",
                    json={
                        "email": _USER_EMAIL,
                        "password": _USER_PASSWORD,
                    },
                )

            resp = await ac.post(
                "/api/v1/auth/login",
                json={
                    "email": _USER_EMAIL,
                    "password": _USER_PASSWORD,
                },
            )
            assert resp.status_code == 429
            body = resp.json()
            assert "error" in body
            assert "Rate limit exceeded" in body["error"]
