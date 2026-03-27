import time
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID

import jwt
import pytest

from loom.config import Settings

# fixed test values
_USER_ID = UUID("01912345-6789-7abc-8def-0123456789ab")
_SECRET = "test-secret-key-that-is-long-enough-for-validation"


@pytest.fixture(autouse=True)
def _mock_settings():
    """provide test settings for all tests."""
    settings = Settings(
        secret_key=_SECRET,
        access_token_expire_minutes=15,
        refresh_token_expire_days=7,
        database_url="sqlite+aiosqlite:///",
    )
    with patch(
        "loom.security.auth.get_settings",
        return_value=settings,
    ):
        yield settings


def test_access_token_includes_jti():
    """access tokens should contain a jti claim."""
    from loom.security.auth import create_access_token, decode_token

    token = create_access_token(str(_USER_ID), "admin")
    payload = decode_token(token)
    assert "jti" in payload
    assert isinstance(payload["jti"], str)
    assert len(payload["jti"]) > 0


def test_refresh_token_includes_jti():
    """refresh tokens should contain a jti claim."""
    from loom.security.auth import create_refresh_token, decode_token

    token = create_refresh_token(str(_USER_ID))
    payload = decode_token(token)
    assert "jti" in payload
    assert isinstance(payload["jti"], str)


def test_each_token_gets_unique_jti():
    """each token should get a different jti."""
    from loom.security.auth import create_access_token, decode_token

    t1 = create_access_token(str(_USER_ID), "admin")
    t2 = create_access_token(str(_USER_ID), "admin")
    p1 = decode_token(t1)
    p2 = decode_token(t2)
    assert p1["jti"] != p2["jti"]


async def test_revoke_token_service():
    """revoke_token should add an entry to the session."""
    from loom.services.token_revocation import revoke_token

    session = AsyncMock()
    # simulate no existing revoked token
    result_mock = MagicMock()
    result_mock.scalar_one_or_none.return_value = None
    session.execute.return_value = result_mock

    expires = datetime.now(UTC) + timedelta(hours=1)
    await revoke_token(session, "test-jti", str(_USER_ID), expires)

    session.add.assert_called_once()
    session.commit.assert_called_once()


async def test_revoke_token_skips_duplicate():
    """revoking the same jti twice should be idempotent."""
    from loom.services.token_revocation import revoke_token

    session = AsyncMock()
    # simulate existing revoked token
    result_mock = MagicMock()
    result_mock.scalar_one_or_none.return_value = UUID(
        "01912345-6789-7abc-8def-0123456789ab"
    )
    session.execute.return_value = result_mock

    expires = datetime.now(UTC) + timedelta(hours=1)
    await revoke_token(session, "test-jti", str(_USER_ID), expires)

    session.add.assert_not_called()


async def test_is_token_revoked_true():
    """is_token_revoked returns true for revoked jti."""
    from loom.services.token_revocation import is_token_revoked

    session = AsyncMock()
    result_mock = MagicMock()
    result_mock.scalar_one_or_none.return_value = UUID(
        "01912345-6789-7abc-8def-0123456789ab"
    )
    session.execute.return_value = result_mock

    assert await is_token_revoked(session, "revoked-jti") is True


async def test_is_token_revoked_false():
    """is_token_revoked returns false for valid jti."""
    from loom.services.token_revocation import is_token_revoked

    session = AsyncMock()
    result_mock = MagicMock()
    result_mock.scalar_one_or_none.return_value = None
    session.execute.return_value = result_mock

    assert await is_token_revoked(session, "valid-jti") is False


async def test_cleanup_expired_tokens():
    """cleanup should delete expired revoked tokens."""
    from loom.services.token_revocation import (
        cleanup_expired_tokens,
    )

    session = AsyncMock()
    result_mock = MagicMock()
    result_mock.rowcount = 5
    session.execute.return_value = result_mock

    count = await cleanup_expired_tokens(session)
    assert count == 5
    session.commit.assert_called_once()


def test_revoked_token_model_fields():
    """revoked token model should have expected columns."""
    from loom.models.revoked_token import RevokedToken

    # verify the table name and column existence
    assert RevokedToken.__tablename__ == "revoked_tokens"
    columns = {c.name for c in RevokedToken.__table__.columns}
    assert "id" in columns
    assert "jti" in columns
    assert "user_id" in columns
    assert "revoked_at" in columns
    assert "expires_at" in columns


def test_revoked_token_jti_is_indexed():
    """jti column should be indexed for fast lookups."""
    from loom.models.revoked_token import RevokedToken

    jti_col = RevokedToken.__table__.columns["jti"]
    assert jti_col.index is True
    assert jti_col.unique is True
