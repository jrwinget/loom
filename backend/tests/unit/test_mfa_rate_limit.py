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


def _make_mfa_user() -> MagicMock:
    from loom.models.user import User

    user = MagicMock(spec=User)
    user.id = _USER_ID
    user.email = _USER_EMAIL
    user.display_name = "MFA User"
    user.role = "admin"
    user.is_active = True
    user.password_hash = _USER_HASH
    user.mfa_enabled = True
    user.mfa_secret = "JBSWY3DPEHPK3PXP"
    user.recovery_codes = None
    user.created_at = datetime(2025, 1, 1, tzinfo=UTC)
    user.updated_at = datetime(2025, 1, 1, tzinfo=UTC)
    return user


class MockSession:
    def __init__(self, *, user=None):
        self._user = user
        self._added: list[object] = []

    async def execute(self, stmt):
        result = MagicMock()
        result.scalar_one_or_none.return_value = (
            self._user
        )
        return result

    def add(self, obj: object) -> None:
        self._added.append(obj)

    async def commit(self) -> None:
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


async def test_mfa_challenge_rate_limit(
    mock_settings: Settings,
) -> None:
    """mfa challenge endpoint returns 429 after 5 attempts."""
    from loom.security.auth import (
        create_mfa_challenge_token,
    )
    from loom.security.rate_limit import limiter

    limiter.reset()

    user = _make_mfa_user()
    session = MockSession(user=user)
    app = _create_app(session, mock_settings)

    with patch(
        "loom.security.auth.get_settings",
        return_value=mock_settings,
    ):
        challenge_token = create_mfa_challenge_token(
            str(_USER_ID)
        )

        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://testserver",
        ) as ac:
            # send 5 requests (at limit)
            for _ in range(5):
                resp = await ac.post(
                    "/api/v1/auth/mfa/challenge",
                    json={
                        "challenge_token": challenge_token,
                        "code": "000000",
                    },
                )
                # 401 = bad code, not rate limited
                assert resp.status_code in (200, 401)

            # 6th request should be rate limited
            resp = await ac.post(
                "/api/v1/auth/mfa/challenge",
                json={
                    "challenge_token": challenge_token,
                    "code": "000000",
                },
            )
            assert resp.status_code == 429
