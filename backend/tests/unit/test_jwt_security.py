"""jwt security attack scenario tests."""

import base64
import json
import time
from unittest.mock import patch

import jwt
import pytest

from loom.config import Settings
from loom.security.auth import (
    create_access_token,
    create_refresh_token,
    decode_token,
)

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


# ── algorithm confusion attacks ───────────────────────────


class TestAlgorithmConfusion:
    """algorithm confusion attack scenarios."""

    def test_none_algorithm_rejected(self) -> None:
        """tokens signed with 'none' algorithm must be rejected."""
        token = create_access_token("user-1", "admin")
        # decode to get payload, re-encode with none
        payload = jwt.decode(token, options={"verify_signature": False})
        forged = jwt.encode(payload, key="", algorithm="none")
        with pytest.raises(jwt.InvalidAlgorithmError):
            decode_token(forged)

    def test_hs384_algorithm_rejected(self) -> None:
        """tokens signed with wrong HS algorithm must fail."""
        payload = {
            "sub": "user-1",
            "role": "admin",
            "type": "access",
        }
        forged = jwt.encode(payload, "wrong-key", algorithm="HS384")
        with pytest.raises(jwt.InvalidAlgorithmError):
            decode_token(forged)

    def test_hs512_algorithm_rejected(self) -> None:
        """tokens signed with HS512 must fail even with
        correct key."""
        payload = {
            "sub": "user-1",
            "role": "admin",
            "exp": time.time() + 3600,
        }
        forged = jwt.encode(payload, _SECRET, algorithm="HS512")
        with pytest.raises(jwt.InvalidAlgorithmError):
            decode_token(forged)

    def test_only_hs256_accepted(self) -> None:
        """only HS256 tokens with correct key succeed."""
        token = create_access_token("user-1", "admin")
        payload = decode_token(token)
        assert payload["sub"] == "user-1"
        assert payload["role"] == "admin"


# ── token tampering attacks ───────────────────────────────


class TestTokenTampering:
    """token payload modification scenarios."""

    def test_modified_role_rejected(self) -> None:
        """modifying the role claim invalidates the
        signature."""
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
        with pytest.raises(jwt.InvalidSignatureError):
            decode_token(forged)

    def test_modified_sub_rejected(self) -> None:
        """modifying the sub claim invalidates the signature."""
        token = create_access_token("user-1", "admin")
        parts = token.split(".")
        payload = json.loads(base64.urlsafe_b64decode(parts[1] + "=="))
        payload["sub"] = "user-999"
        forged_payload = (
            base64.urlsafe_b64encode(json.dumps(payload).encode())
            .rstrip(b"=")
            .decode()
        )
        forged = f"{parts[0]}.{forged_payload}.{parts[2]}"
        with pytest.raises(jwt.InvalidSignatureError):
            decode_token(forged)

    def test_expired_token_rejected(self) -> None:
        """tokens with expired timestamps must be rejected."""
        payload = {
            "sub": "user-1",
            "role": "admin",
            "jti": "test-jti",
            "exp": time.time() - 60,
        }
        token = jwt.encode(payload, _SECRET, algorithm="HS256")
        with pytest.raises(jwt.ExpiredSignatureError):
            decode_token(token)

    def test_truncated_signature_rejected(self) -> None:
        """token with truncated signature must fail."""
        token = create_access_token("user-1", "admin")
        parts = token.split(".")
        # truncate signature to half
        truncated_sig = parts[2][: len(parts[2]) // 2]
        forged = f"{parts[0]}.{parts[1]}.{truncated_sig}"
        with pytest.raises(jwt.DecodeError):
            decode_token(forged)

    def test_empty_signature_rejected(self) -> None:
        """token with empty signature must fail."""
        token = create_access_token("user-1", "admin")
        parts = token.split(".")
        forged = f"{parts[0]}.{parts[1]}."
        with pytest.raises(jwt.InvalidSignatureError):
            decode_token(forged)

    def test_wrong_secret_rejected(self) -> None:
        """token signed with different secret must fail."""
        payload = {
            "sub": "user-1",
            "role": "admin",
            "exp": time.time() + 3600,
        }
        token = jwt.encode(payload, "different-secret", algorithm="HS256")
        with pytest.raises(jwt.InvalidSignatureError):
            decode_token(token)


# ── refresh token security ────────────────────────────────


class TestRefreshTokenSecurity:
    """refresh token specific security tests."""

    def test_access_token_lacks_refresh_type(self) -> None:
        """access tokens must not have type=refresh."""
        token = create_access_token("user-1", "admin")
        payload = decode_token(token)
        assert payload.get("type") != "refresh"

    def test_refresh_token_has_type_refresh(self) -> None:
        """refresh tokens must carry type=refresh."""
        token = create_refresh_token("user-1")
        payload = decode_token(token)
        assert payload["type"] == "refresh"

    def test_refresh_token_has_jti(self) -> None:
        """refresh tokens must have a jti for revocation."""
        token = create_refresh_token("user-1")
        payload = decode_token(token)
        assert "jti" in payload
        assert payload["jti"]  # not empty

    def test_access_token_has_jti(self) -> None:
        """access tokens must also carry a jti."""
        token = create_access_token("user-1", "admin")
        payload = decode_token(token)
        assert "jti" in payload
        assert payload["jti"]

    def test_refresh_token_has_no_role(self) -> None:
        """refresh tokens should not carry a role claim."""
        token = create_refresh_token("user-1")
        payload = decode_token(token)
        assert "role" not in payload

    def test_refresh_tokens_have_unique_jti(self) -> None:
        """each refresh token must have a distinct jti."""
        t1 = create_refresh_token("user-1")
        t2 = create_refresh_token("user-1")
        p1 = decode_token(t1)
        p2 = decode_token(t2)
        assert p1["jti"] != p2["jti"]
