"""jwt security attack scenario tests."""

import base64
import json
from unittest.mock import patch

import jwt
import pytest

from loom.config import Settings
from loom.security.auth import (
    create_access_token,
    create_refresh_token,
    decode_token,
)


@pytest.fixture(autouse=True)
def _mock_settings():
    """provide test settings for all tests."""
    settings = Settings(
        secret_key=("test-secret-key-that-is-long-enough-for-validation"),
        access_token_expire_minutes=15,
        refresh_token_expire_days=7,
        database_url="sqlite+aiosqlite:///",
    )
    with patch(
        "loom.security.auth.get_settings",
        return_value=settings,
    ):
        yield settings


class TestAlgorithmConfusion:
    """algorithm confusion attack scenarios."""

    def test_none_algorithm_rejected(self) -> None:
        """tokens signed with 'none' must be rejected."""
        token = create_access_token("user-1", "admin")
        payload = jwt.decode(token, options={"verify_signature": False})
        forged = jwt.encode(payload, key="", algorithm="none")
        with pytest.raises((jwt.PyJWTError, ValueError)):
            decode_token(forged)

    def test_hs384_algorithm_rejected(self) -> None:
        """tokens signed with wrong algorithm must fail."""
        payload = {
            "sub": "user-1",
            "role": "admin",
            "type": "access",
        }
        forged = jwt.encode(payload, "wrong-key", algorithm="HS384")
        with pytest.raises((jwt.PyJWTError, ValueError)):
            decode_token(forged)

    def test_wrong_secret_rejected(self) -> None:
        """tokens signed with wrong secret must fail."""
        payload = {
            "sub": "user-1",
            "role": "admin",
            "type": "access",
        }
        forged = jwt.encode(payload, "not-the-right-key", algorithm="HS256")
        with pytest.raises((jwt.PyJWTError, ValueError)):
            decode_token(forged)


class TestTokenTampering:
    """token payload modification scenarios."""

    def test_modified_role_rejected(self) -> None:
        """modifying the role claim invalidates signature."""
        token = create_access_token("user-1", "viewer")
        parts = token.split(".")
        payload = json.loads(base64.urlsafe_b64decode(parts[1] + "=="))
        payload["role"] = "admin"
        forged_payload = (
            base64.urlsafe_b64encode(json.dumps(payload).encode())
            .rstrip(b"=")
            .decode()
        )
        forged = f"{parts[0]}.{forged_payload}.{parts[2]}"
        with pytest.raises((jwt.PyJWTError, ValueError)):
            decode_token(forged)

    def test_modified_sub_rejected(self) -> None:
        """modifying the sub claim invalidates signature."""
        token = create_access_token("user-1", "viewer")
        parts = token.split(".")
        payload = json.loads(base64.urlsafe_b64decode(parts[1] + "=="))
        payload["sub"] = "admin-user"
        forged_payload = (
            base64.urlsafe_b64encode(json.dumps(payload).encode())
            .rstrip(b"=")
            .decode()
        )
        forged = f"{parts[0]}.{forged_payload}.{parts[2]}"
        with pytest.raises((jwt.PyJWTError, ValueError)):
            decode_token(forged)

    def test_empty_token_rejected(self) -> None:
        """empty string must be rejected."""
        with pytest.raises((jwt.PyJWTError, ValueError)):
            decode_token("")

    def test_garbage_token_rejected(self) -> None:
        """random garbage must be rejected."""
        with pytest.raises((jwt.PyJWTError, ValueError)):
            decode_token("not.a.jwt")


class TestRefreshTokenSecurity:
    """refresh token specific security tests."""

    def test_access_token_has_no_refresh_type(self) -> None:
        """access tokens must not have type=refresh."""
        token = create_access_token("user-1", "admin")
        payload = decode_token(token)
        assert payload.get("type") != "refresh"

    def test_refresh_token_type_is_refresh(self) -> None:
        """refresh tokens have type=refresh."""
        token = create_refresh_token("user-1")
        payload = decode_token(token)
        assert payload.get("type") == "refresh"

    def test_refresh_token_has_jti(self) -> None:
        """refresh tokens must have a jti for revocation."""
        token = create_refresh_token("user-1")
        payload = decode_token(token)
        assert "jti" in payload
        assert payload["jti"]

    def test_access_token_has_role(self) -> None:
        """access tokens must include the role claim."""
        token = create_access_token("user-1", "analyst")
        payload = decode_token(token)
        assert payload["role"] == "analyst"

    def test_two_refresh_tokens_have_different_jti(
        self,
    ) -> None:
        """each refresh token must have a unique jti."""
        t1 = create_refresh_token("user-1")
        t2 = create_refresh_token("user-1")
        p1 = decode_token(t1)
        p2 = decode_token(t2)
        assert p1["jti"] != p2["jti"]
