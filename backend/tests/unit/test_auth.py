import time
from unittest.mock import AsyncMock, MagicMock, patch

import jwt
import pytest
from fastapi import HTTPException, status
from starlette.requests import Request

from loom.config import Settings
from loom.security.auth import (
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)


@pytest.fixture(autouse=True)
def _mock_settings():
    """provide test settings for all tests."""
    settings = Settings(
        secret_key="test-secret-key-that-is-long-enough-for-validation",
        access_token_expire_minutes=15,
        refresh_token_expire_days=7,
        database_url="sqlite+aiosqlite:///",
    )
    with patch(
        "loom.security.auth.get_settings",
        return_value=settings,
    ):
        yield settings


def test_hash_password_returns_string():
    hashed = hash_password("testpassword")
    assert isinstance(hashed, str)
    assert hashed != "testpassword"


def test_verify_password_correct():
    hashed = hash_password("testpassword")
    assert verify_password("testpassword", hashed) is True


def test_verify_password_incorrect():
    hashed = hash_password("testpassword")
    assert verify_password("wrongpassword", hashed) is False


def test_create_access_token_and_decode():
    token = create_access_token("user-123", "admin")
    payload = decode_token(token)
    assert payload["sub"] == "user-123"
    assert payload["role"] == "admin"
    assert "exp" in payload


def test_create_refresh_token_and_decode():
    token = create_refresh_token("user-456")
    payload = decode_token(token)
    assert payload["sub"] == "user-456"
    assert payload["type"] == "refresh"
    assert "exp" in payload


def test_expired_token_rejected(_mock_settings):
    """create a token that is already expired."""
    settings = _mock_settings
    payload = {
        "sub": "user-789",
        "role": "admin",
        "exp": time.time() - 10,
    }
    token = jwt.encode(
        payload,
        settings.secret_key,
        algorithm="HS256",
    )
    with pytest.raises(jwt.ExpiredSignatureError):
        decode_token(token)


def test_invalid_token_rejected():
    with pytest.raises(jwt.DecodeError):
        decode_token("not-a-valid-token")


@pytest.mark.asyncio
async def test_login_constant_timing_calls_verify_on_missing_user(
    _mock_settings,
):
    """verify_password is called even when user is not found."""
    from loom.api.v1.auth import login
    from loom.schemas.user import UserLogin

    body = UserLogin(email="no@exist.com", password="NoExist123xx")

    # mock db to return no user
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    mock_db = AsyncMock()
    mock_db.execute = AsyncMock(return_value=mock_result)

    mock_request = MagicMock(spec=Request)
    mock_request.client.host = "127.0.0.1"
    mock_request.headers = {}
    mock_request.state = MagicMock()

    with patch(
        "loom.api.v1.auth.verify_password",
        return_value=False,
    ) as mock_verify:
        with pytest.raises(HTTPException) as exc_info:
            await login(
                request=mock_request,
                body=body,
                session=mock_db,
            )
        assert exc_info.value.status_code == status.HTTP_401_UNAUTHORIZED
        assert mock_verify.call_count == 1


@pytest.mark.asyncio
async def test_refresh_allows_through_on_revocation_check_error(
    _mock_settings,
):
    """refresh succeeds when revocation check raises (fail-open)."""
    from loom.api.v1.auth import refresh
    from loom.schemas.user import TokenRefresh

    token = create_refresh_token("user-123")
    body = TokenRefresh(refresh_token=token)

    mock_request = MagicMock(spec=Request)
    mock_request.client.host = "127.0.0.1"
    mock_request.headers = {}
    mock_request.state = MagicMock()

    # mock db to return a valid active user after the
    # revocation check is skipped
    mock_user = MagicMock()
    mock_user.id = "user-123"
    mock_user.role = "analyst"
    mock_user.is_active = True

    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = mock_user
    mock_db = AsyncMock()
    mock_db.execute = AsyncMock(return_value=mock_result)

    with (
        patch(
            "loom.services.token_revocation.is_token_revoked",
            side_effect=RuntimeError("db down"),
        ),
        patch(
            "loom.api.v1.auth.revoke_token",
            new_callable=AsyncMock,
        ),
    ):
        result = await refresh(
            body=body,
            request=mock_request,
            session=mock_db,
        )
    assert result.access_token is not None
    assert result.token_type == "bearer"


@pytest.mark.asyncio
async def test_rbac_allows_through_on_db_error(_mock_settings):
    """rbac allows request through when revocation check raises."""
    from loom.security.rbac import _extract_token

    token = create_access_token("user-123", "admin")
    mock_request = MagicMock()
    mock_request.headers.get.return_value = f"Bearer {token}"

    # mock the session factory to raise
    mock_session = AsyncMock()
    mock_session.execute = AsyncMock(
        side_effect=RuntimeError("db down"),
    )
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)

    mock_factory = MagicMock(return_value=mock_session)
    mock_request.app.state.db_session_factory = mock_factory

    # fail-open: request passes through when db is down
    payload = await _extract_token(mock_request)
    assert payload["sub"] == "user-123"
    assert payload["role"] == "admin"
