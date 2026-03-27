from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError

from loom.config import get_settings

_ph = PasswordHasher()


def hash_password(password: str) -> str:
    """hash a password using argon2."""
    return _ph.hash(password)


def verify_password(password: str, hash: str) -> bool:
    """verify a password against an argon2 hash."""
    try:
        return _ph.verify(hash, password)
    except VerifyMismatchError:
        return False


def create_access_token(user_id: str, role: str) -> str:
    """create a short-lived jwt access token."""
    settings = get_settings()
    payload = {
        "sub": user_id,
        "role": role,
        "jti": str(uuid4()),
        "exp": datetime.now(UTC)
        + timedelta(minutes=settings.access_token_expire_minutes),
    }
    return jwt.encode(
        payload,
        settings.secret_key,
        algorithm="HS256",
    )


def create_refresh_token(user_id: str) -> str:
    """create a longer-lived jwt refresh token."""
    settings = get_settings()
    payload = {
        "sub": user_id,
        "type": "refresh",
        "jti": str(uuid4()),
        "exp": datetime.now(UTC)
        + timedelta(days=settings.refresh_token_expire_days),
    }
    return jwt.encode(
        payload,
        settings.secret_key,
        algorithm="HS256",
    )


def decode_token(token: str) -> dict[str, Any]:
    """decode and verify a jwt token."""
    settings = get_settings()
    return jwt.decode(
        token,
        settings.secret_key,
        algorithms=["HS256"],
    )
