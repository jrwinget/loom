"""tests for POST /api/v1/auth/recover-password."""

from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import Any
from unittest.mock import MagicMock, patch
from uuid import UUID

import httpx
import pytest
import pytest_asyncio

from loom.config import Settings, get_settings
from loom.dependencies import get_db_session
from loom.models.audit import AuditLogEntry
from loom.models.user import User
from loom.security.auth import hash_password, verify_password
from loom.security.password_recovery import (
    generate_codes,
    hash_code,
    serialize,
)
from loom.security.rate_limit import limiter

_USER_ID = UUID("01912345-6789-7abc-8def-0123456789ab")
_USER_EMAIL = "ada@example.org"
_OLD_PASSWORD = "OriginalPass-12"
_NEW_PASSWORD = "BrandNewPass-99"


@pytest.fixture(autouse=True)
def _reset_rate_limiter() -> None:
    # the recover-password endpoint is rate-limited 3/hour; without
    # resetting between tests later cases would hit 429 and mask the
    # real status code being asserted on.
    limiter.reset()


def _make_user(
    *,
    codes: list[str] | None = None,
    is_active: bool = True,
) -> MagicMock:
    """build a mock user whose stored codes match the given plaintexts."""
    user = MagicMock(spec=User)
    user.id = _USER_ID
    user.email = _USER_EMAIL
    user.display_name = "Ada Lovelace"
    user.role = "admin"
    user.is_active = is_active
    user.password_hash = hash_password(_OLD_PASSWORD)
    user.mfa_enabled = False
    user.password_recovery_codes = (
        serialize([hash_code(c) for c in codes]) if codes else None
    )
    user.created_at = datetime(2025, 1, 1, tzinfo=UTC)
    user.updated_at = datetime(2025, 1, 1, tzinfo=UTC)
    return user


class _Session:
    """mock async session that returns ``user`` for any User select."""

    def __init__(self, *, user: object | None) -> None:
        self._user = user
        self.added: list[object] = []
        self.commits = 0

    async def execute(self, stmt: Any) -> MagicMock:
        result = MagicMock()
        # the endpoint only ever issues `select(User).where(...)`.
        # anything else (revoked-token checks etc.) gets a None scalar
        # so the request isn't blocked by an unrelated side effect.
        result.scalar_one_or_none.return_value = self._user
        return result

    def add(self, obj: object) -> None:
        self.added.append(obj)

    async def commit(self) -> None:
        self.commits += 1

    async def rollback(self) -> None:
        return None

    async def refresh(self, obj: object) -> None:
        return None


@pytest_asyncio.fixture
def mock_settings() -> Settings:
    return Settings(
        secret_key="test-secret-key-that-is-long-enough-for-validation",
        access_token_expire_minutes=15,
        refresh_token_expire_days=7,
        database_url="sqlite+aiosqlite:///",
    )


def _build_app(session: _Session, settings: Settings) -> Any:
    get_settings.cache_clear()
    with patch("loom.config.get_settings", return_value=settings):
        from loom.main import create_app

        application = create_app()

    async def override_db() -> AsyncIterator[_Session]:
        yield session

    application.dependency_overrides[get_db_session] = override_db
    application.state.db_session_factory = None
    return application


async def _post_recover(
    app: Any,
    payload: dict[str, str],
    settings: Settings,
) -> httpx.Response:
    with patch("loom.security.auth.get_settings", return_value=settings):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://testserver",
        ) as ac:
            return await ac.post("/api/v1/auth/recover-password", json=payload)


async def test_happy_path_rotates_password_and_consumes_code(
    mock_settings: Settings,
) -> None:
    codes = generate_codes()
    user = _make_user(codes=codes)
    session = _Session(user=user)
    app = _build_app(session, mock_settings)

    resp = await _post_recover(
        app,
        {
            "email": _USER_EMAIL,
            "recovery_code": codes[0],
            "new_password": _NEW_PASSWORD,
        },
        mock_settings,
    )

    assert resp.status_code == 200
    assert resp.json()["codes_remaining"] == 7

    # password hash was rotated and verifies against the new password
    assert verify_password(_NEW_PASSWORD, user.password_hash)
    # used code was removed from the stored set
    assert hash_code(codes[0]) not in (user.password_recovery_codes or "")
    # remaining hashes are still present (sample one)
    assert hash_code(codes[1]) in (user.password_recovery_codes or "")

    # audit row was queued
    audit = [a for a in session.added if isinstance(a, AuditLogEntry)]
    assert len(audit) == 1
    assert audit[0].action == "user.password.recover"
    assert str(audit[0].resource_id) == str(_USER_ID)


async def test_hyphenated_and_raw_forms_both_succeed(
    mock_settings: Settings,
) -> None:
    codes = generate_codes()
    user = _make_user(codes=codes)
    session = _Session(user=user)
    app = _build_app(session, mock_settings)

    resp = await _post_recover(
        app,
        {
            "email": _USER_EMAIL,
            "recovery_code": codes[0].replace("-", ""),
            "new_password": _NEW_PASSWORD,
        },
        mock_settings,
    )
    assert resp.status_code == 200


async def test_already_used_code_rejected(
    mock_settings: Settings,
) -> None:
    codes = generate_codes()
    user = _make_user(codes=codes)
    session = _Session(user=user)
    app = _build_app(session, mock_settings)

    first = await _post_recover(
        app,
        {
            "email": _USER_EMAIL,
            "recovery_code": codes[0],
            "new_password": _NEW_PASSWORD,
        },
        mock_settings,
    )
    assert first.status_code == 200

    second = await _post_recover(
        app,
        {
            "email": _USER_EMAIL,
            "recovery_code": codes[0],
            "new_password": "AnotherPass-22",
        },
        mock_settings,
    )
    assert second.status_code == 401


async def test_unknown_email_returns_401_with_same_detail_as_wrong_code(
    mock_settings: Settings,
) -> None:
    # session returns None — pretend the email is unknown
    session = _Session(user=None)
    app = _build_app(session, mock_settings)

    resp = await _post_recover(
        app,
        {
            "email": "ghost@example.org",
            "recovery_code": "aaaaa-bbbbb-ccccc-ddddd",
            "new_password": _NEW_PASSWORD,
        },
        mock_settings,
    )
    assert resp.status_code == 401
    assert resp.json()["detail"] == "invalid email or recovery code"


async def test_wrong_code_returns_same_detail_as_unknown_email(
    mock_settings: Settings,
) -> None:
    codes = generate_codes()
    user = _make_user(codes=codes)
    session = _Session(user=user)
    app = _build_app(session, mock_settings)

    resp = await _post_recover(
        app,
        {
            "email": _USER_EMAIL,
            "recovery_code": "zzzzz-yyyyy-xxxxx-wwwww",
            "new_password": _NEW_PASSWORD,
        },
        mock_settings,
    )
    assert resp.status_code == 401
    assert resp.json()["detail"] == "invalid email or recovery code"
    # password must NOT have been rotated
    assert verify_password(_OLD_PASSWORD, user.password_hash)


async def test_inactive_user_rejected(
    mock_settings: Settings,
) -> None:
    codes = generate_codes()
    user = _make_user(codes=codes, is_active=False)
    session = _Session(user=user)
    app = _build_app(session, mock_settings)

    resp = await _post_recover(
        app,
        {
            "email": _USER_EMAIL,
            "recovery_code": codes[0],
            "new_password": _NEW_PASSWORD,
        },
        mock_settings,
    )
    assert resp.status_code == 401
    # deactivation must not leak: same detail string
    assert resp.json()["detail"] == "invalid email or recovery code"


async def test_weak_new_password_rejected_with_422(
    mock_settings: Settings,
) -> None:
    codes = generate_codes()
    user = _make_user(codes=codes)
    session = _Session(user=user)
    app = _build_app(session, mock_settings)

    resp = await _post_recover(
        app,
        {
            "email": _USER_EMAIL,
            "recovery_code": codes[0],
            "new_password": "alllowercase",
        },
        mock_settings,
    )
    assert resp.status_code == 422
    # password complexity violation — user must NOT have been mutated
    assert verify_password(_OLD_PASSWORD, user.password_hash)


async def test_last_code_consumed_sets_remaining_to_zero(
    mock_settings: Settings,
) -> None:
    code = generate_codes()[0]
    user = _make_user(codes=[code])
    session = _Session(user=user)
    app = _build_app(session, mock_settings)

    resp = await _post_recover(
        app,
        {
            "email": _USER_EMAIL,
            "recovery_code": code,
            "new_password": _NEW_PASSWORD,
        },
        mock_settings,
    )
    assert resp.status_code == 200
    assert resp.json()["codes_remaining"] == 0
    # column should be NULL when all codes are spent
    assert user.password_recovery_codes is None
