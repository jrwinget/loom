from datetime import UTC, datetime
from unittest.mock import MagicMock, patch
from uuid import UUID

import httpx
import pytest_asyncio

from loom.config import Settings, get_settings
from loom.dependencies import get_db_session
from loom.security.auth import hash_password

_USER_ID = UUID("01912345-6789-7abc-8def-0123456789ab")
_USER_EMAIL = "mfa@example.com"
_USER_PASSWORD = "securepassword123"
_USER_HASH = hash_password(_USER_PASSWORD)


def _make_user(*, mfa_enabled: bool = False) -> MagicMock:
    from loom.models.user import User

    user = MagicMock(spec=User)
    user.id = _USER_ID
    user.email = _USER_EMAIL
    user.display_name = "Test User"
    user.role = "admin"
    user.is_active = True
    user.password_hash = _USER_HASH
    user.mfa_enabled = mfa_enabled
    user.mfa_secret = (
        "JBSWY3DPEHPK3PXP" if mfa_enabled else None
    )
    user.recovery_codes = None
    user.created_at = datetime(2025, 1, 1, tzinfo=UTC)
    user.updated_at = datetime(2025, 1, 1, tzinfo=UTC)
    return user


class MockSession:
    def __init__(self, *, user=None, user_count: int = 1):
        self._user = user
        self._user_count = user_count
        self._added: list[object] = []

    async def execute(self, stmt):
        stmt_str = str(stmt)
        if "count" in stmt_str.lower():
            result = MagicMock()
            result.scalar_one.return_value = (
                self._user_count
            )
            return result
        result = MagicMock()
        result.scalar_one_or_none.return_value = (
            self._user
        )
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
        secret_key=(
            "test-secret-key-that-is-long-enough-for-validation"
        ),
        access_token_expire_minutes=15,
        refresh_token_expire_days=7,
        database_url="sqlite+aiosqlite:///",
    )


def _create_app(mock_session, settings):
    get_settings.cache_clear()
    with patch(
        "loom.config.get_settings", return_value=settings
    ):
        from loom.main import create_app

        application = create_app()

    async def override_db():
        yield mock_session

    application.dependency_overrides[get_db_session] = (
        override_db
    )
    application.state.db_session_factory = None
    return application


async def test_login_mfa_user_returns_challenge(
    mock_settings: Settings,
) -> None:
    """mfa-enabled user gets challenge_token, not jwt."""
    from loom.security.rate_limit import limiter

    limiter.reset()

    user = _make_user(mfa_enabled=True)
    session = MockSession(user=user)
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
                    "email": _USER_EMAIL,
                    "password": _USER_PASSWORD,
                },
            )
            assert resp.status_code == 200
            body = resp.json()
            assert body["requires_mfa"] is True
            assert "challenge_token" in body
            assert "access_token" not in body


async def test_login_non_mfa_user_returns_tokens(
    mock_settings: Settings,
) -> None:
    """non-mfa user gets normal jwt tokens."""
    from loom.security.rate_limit import limiter

    limiter.reset()

    user = _make_user(mfa_enabled=False)
    session = MockSession(user=user)
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
                    "email": _USER_EMAIL,
                    "password": _USER_PASSWORD,
                },
            )
            assert resp.status_code == 200
            body = resp.json()
            assert "access_token" in body
            assert "refresh_token" in body
            assert "requires_mfa" not in body
