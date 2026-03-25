import time
from unittest.mock import patch

import jwt
import pytest

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
        secret_key="test-secret-key",
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
