import hashlib
from unittest.mock import AsyncMock, MagicMock, patch

import pyotp
import pytest
from fastapi import HTTPException, status

from loom.config import Settings
from loom.security.auth import (
    create_access_token,
    create_mfa_challenge_token,
    decode_token,
)


@pytest.fixture(autouse=True)
def _mock_settings():
    settings = Settings(
        secret_key=(
            "test-secret-key-that-is-long-enough"
            "-for-validation"
        ),
        access_token_expire_minutes=15,
        refresh_token_expire_days=7,
        database_url="sqlite+aiosqlite:///",
    )
    with patch(
        "loom.security.auth.get_settings",
        return_value=settings,
    ):
        yield settings


def _make_user(
    mfa_enabled: bool = False,
    mfa_secret: str | None = None,
    recovery_codes: str | None = None,
) -> MagicMock:
    user = MagicMock()
    user.id = "00000000-0000-0000-0000-000000000001"
    user.email = "test@example.com"
    user.display_name = "Test User"
    user.role = "analyst"
    user.is_active = True
    user.mfa_enabled = mfa_enabled
    user.mfa_secret = mfa_secret
    user.recovery_codes = recovery_codes
    return user


def _mock_db_with_user(user: MagicMock) -> AsyncMock:
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = user
    db = AsyncMock()
    db.execute = AsyncMock(return_value=mock_result)
    db.add = MagicMock()
    db.commit = AsyncMock()
    db.refresh = AsyncMock()
    return db


def test_create_mfa_challenge_token():
    token = create_mfa_challenge_token("user-123")
    payload = decode_token(token)
    assert payload["sub"] == "user-123"
    assert payload["type"] == "mfa_challenge"
    assert "exp" in payload


@pytest.mark.asyncio
async def test_mfa_setup_generates_secret():
    from loom.api.v1.mfa import mfa_setup

    user = _make_user()
    db = _mock_db_with_user(user)
    payload = {"sub": str(user.id), "role": "analyst"}

    result = await mfa_setup(
        token_payload=payload,
        session=db,
    )

    assert "otpauth://" in result.provisioning_uri
    assert result.mfa_enabled is False
    assert user.mfa_secret is not None


@pytest.mark.asyncio
async def test_mfa_setup_fails_if_already_enabled():
    from loom.api.v1.mfa import mfa_setup

    user = _make_user(mfa_enabled=True)
    db = _mock_db_with_user(user)
    payload = {"sub": str(user.id), "role": "analyst"}

    with pytest.raises(HTTPException) as exc_info:
        await mfa_setup(
            token_payload=payload,
            session=db,
        )
    assert (
        exc_info.value.status_code
        == status.HTTP_400_BAD_REQUEST
    )


@pytest.mark.asyncio
async def test_mfa_verify_enables_mfa():
    from loom.api.v1.mfa import mfa_verify
    from loom.schemas.mfa import MfaVerifyRequest

    secret = pyotp.random_base32()
    totp = pyotp.TOTP(secret)
    code = totp.now()

    user = _make_user(mfa_secret=secret)
    db = _mock_db_with_user(user)
    payload = {"sub": str(user.id), "role": "analyst"}

    result = await mfa_verify(
        body=MfaVerifyRequest(code=code),
        token_payload=payload,
        session=db,
    )

    assert result.mfa_enabled is True
    assert len(result.recovery_codes) == 10
    assert user.mfa_enabled is True
    assert user.recovery_codes is not None


@pytest.mark.asyncio
async def test_mfa_verify_rejects_bad_code():
    from loom.api.v1.mfa import mfa_verify
    from loom.schemas.mfa import MfaVerifyRequest

    secret = pyotp.random_base32()
    user = _make_user(mfa_secret=secret)
    db = _mock_db_with_user(user)
    payload = {"sub": str(user.id), "role": "analyst"}

    with pytest.raises(HTTPException) as exc_info:
        await mfa_verify(
            body=MfaVerifyRequest(code="000000"),
            token_payload=payload,
            session=db,
        )
    assert (
        exc_info.value.status_code
        == status.HTTP_401_UNAUTHORIZED
    )


@pytest.mark.asyncio
async def test_mfa_challenge_success():
    from loom.api.v1.mfa import mfa_challenge
    from loom.schemas.mfa import MfaChallengeRequest

    secret = pyotp.random_base32()
    totp = pyotp.TOTP(secret)
    code = totp.now()

    user = _make_user(
        mfa_enabled=True, mfa_secret=secret
    )
    db = _mock_db_with_user(user)

    challenge_token = create_mfa_challenge_token(
        str(user.id)
    )

    result = await mfa_challenge(
        body=MfaChallengeRequest(
            challenge_token=challenge_token,
            code=code,
        ),
        session=db,
    )

    assert result.access_token is not None
    assert result.refresh_token is not None
    assert result.token_type == "bearer"


@pytest.mark.asyncio
async def test_mfa_challenge_fails_bad_code():
    from loom.api.v1.mfa import mfa_challenge
    from loom.schemas.mfa import MfaChallengeRequest

    secret = pyotp.random_base32()
    user = _make_user(
        mfa_enabled=True, mfa_secret=secret
    )
    db = _mock_db_with_user(user)

    challenge_token = create_mfa_challenge_token(
        str(user.id)
    )

    with pytest.raises(HTTPException) as exc_info:
        await mfa_challenge(
            body=MfaChallengeRequest(
                challenge_token=challenge_token,
                code="000000",
            ),
            session=db,
        )
    assert (
        exc_info.value.status_code
        == status.HTTP_401_UNAUTHORIZED
    )


@pytest.mark.asyncio
async def test_mfa_challenge_with_recovery_code():
    from loom.api.v1.mfa import mfa_challenge
    from loom.schemas.mfa import MfaChallengeRequest

    secret = pyotp.random_base32()
    recovery = "abcd1234"
    hashed = hashlib.sha256(
        recovery.encode()
    ).hexdigest()

    user = _make_user(
        mfa_enabled=True,
        mfa_secret=secret,
        recovery_codes=hashed,
    )
    db = _mock_db_with_user(user)

    challenge_token = create_mfa_challenge_token(
        str(user.id)
    )

    result = await mfa_challenge(
        body=MfaChallengeRequest(
            challenge_token=challenge_token,
            code=recovery,
        ),
        session=db,
    )

    assert result.access_token is not None
    # recovery code consumed
    assert user.recovery_codes is None


@pytest.mark.asyncio
async def test_mfa_disable_success():
    from loom.api.v1.mfa import mfa_disable
    from loom.schemas.mfa import MfaDisableRequest

    secret = pyotp.random_base32()
    totp = pyotp.TOTP(secret)
    code = totp.now()

    user = _make_user(
        mfa_enabled=True,
        mfa_secret=secret,
        recovery_codes="hash1,hash2",
    )
    db = _mock_db_with_user(user)
    payload = {"sub": str(user.id), "role": "analyst"}

    await mfa_disable(
        body=MfaDisableRequest(code=code),
        token_payload=payload,
        session=db,
    )

    assert user.mfa_enabled is False
    assert user.mfa_secret is None
    assert user.recovery_codes is None


@pytest.mark.asyncio
async def test_mfa_disable_rejects_bad_code():
    from loom.api.v1.mfa import mfa_disable
    from loom.schemas.mfa import MfaDisableRequest

    secret = pyotp.random_base32()
    user = _make_user(
        mfa_enabled=True, mfa_secret=secret
    )
    db = _mock_db_with_user(user)
    payload = {"sub": str(user.id), "role": "analyst"}

    with pytest.raises(HTTPException) as exc_info:
        await mfa_disable(
            body=MfaDisableRequest(code="000000"),
            token_payload=payload,
            session=db,
        )
    assert (
        exc_info.value.status_code
        == status.HTTP_401_UNAUTHORIZED
    )


@pytest.mark.asyncio
async def test_login_returns_mfa_challenge():
    from loom.api.v1.auth import login
    from loom.schemas.user import UserLogin

    user = _make_user(mfa_enabled=True)
    user.password_hash = "hashed"

    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = user
    db = AsyncMock()
    db.execute = AsyncMock(return_value=mock_result)

    body = UserLogin(
        email="test@example.com",
        password="TestPass123!",
    )

    mock_request = MagicMock()
    mock_request.client.host = "127.0.0.1"
    mock_request.headers = {}
    mock_request.state = MagicMock()

    with patch(
        "loom.api.v1.auth.verify_password",
        return_value=True,
    ):
        result = await login(
            request=mock_request,
            body=body,
            session=db,
        )

    assert result["requires_mfa"] is True
    assert "challenge_token" in result


@pytest.mark.asyncio
async def test_mfa_challenge_rejects_wrong_token_type():
    from loom.api.v1.mfa import mfa_challenge
    from loom.schemas.mfa import MfaChallengeRequest

    # use a regular access token instead of challenge
    token = create_access_token("user-123", "analyst")

    user = _make_user(mfa_enabled=True)
    db = _mock_db_with_user(user)

    with pytest.raises(HTTPException) as exc_info:
        await mfa_challenge(
            body=MfaChallengeRequest(
                challenge_token=token,
                code="123456",
            ),
            session=db,
        )
    assert (
        exc_info.value.status_code
        == status.HTTP_401_UNAUTHORIZED
    )
