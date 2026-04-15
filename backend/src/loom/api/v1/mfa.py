import hashlib
import logging
import secrets
from collections.abc import AsyncIterator
from typing import Any

import pyotp
from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Request,
    status,
)
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from loom.dependencies import get_db_session
from loom.models.audit import AuditLogEntry
from loom.models.user import User
from loom.schemas.mfa import (
    MfaChallengeRequest,
    MfaChallengeResponse,
    MfaDisableRequest,
    MfaSetupResponse,
    MfaVerifyRequest,
    MfaVerifyResponse,
)
from loom.security.auth import (
    create_access_token,
    create_refresh_token,
    decode_token,
)
from loom.security.rate_limit import limiter
from loom.security.rbac import (
    get_current_user_id,
    require_authenticated,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth/mfa", tags=["mfa"])

_RECOVERY_CODE_COUNT = 10
_RECOVERY_CODE_LENGTH = 8


def _hash_code(code: str) -> str:
    return hashlib.sha256(code.encode()).hexdigest()


def _generate_recovery_codes() -> list[str]:
    return [
        secrets.token_hex(_RECOVERY_CODE_LENGTH // 2)
        for _ in range(_RECOVERY_CODE_COUNT)
    ]


async def _get_user(db: AsyncSession, user_id: str) -> User:
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="user not found",
        )
    return user


async def _audit(
    db: AsyncSession,
    actor_id: str,
    action: str,
    detail: dict[str, object] | None = None,
) -> None:
    entry = AuditLogEntry(
        actor_id=actor_id,
        action=action,
        resource_type="user",
        resource_id=actor_id,
        detail=detail,
    )
    db.add(entry)


@router.post("/setup", response_model=MfaSetupResponse)
async def mfa_setup(
    token_payload: dict[str, Any] = Depends(  # noqa: B008
        require_authenticated
    ),
    session: AsyncIterator[AsyncSession] = Depends(  # noqa: B008
        get_db_session
    ),
) -> MfaSetupResponse:
    """generate totp secret and provisioning uri."""
    db: AsyncSession = session  # type: ignore[assignment]
    user_id = get_current_user_id(token_payload)
    user = await _get_user(db, user_id)

    if user.mfa_enabled:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="mfa is already enabled",
        )

    secret = pyotp.random_base32()
    user.mfa_secret = secret

    totp = pyotp.TOTP(secret)
    uri = totp.provisioning_uri(name=user.email, issuer_name="Loom")

    await _audit(db, user_id, "mfa_setup_initiated")
    await db.commit()

    return MfaSetupResponse(provisioning_uri=uri)


@router.post("/verify", response_model=MfaVerifyResponse)
async def mfa_verify(
    body: MfaVerifyRequest,
    token_payload: dict[str, Any] = Depends(  # noqa: B008
        require_authenticated
    ),
    session: AsyncIterator[AsyncSession] = Depends(  # noqa: B008
        get_db_session
    ),
) -> MfaVerifyResponse:
    """verify totp code to enable mfa, return recovery codes."""
    db: AsyncSession = session  # type: ignore[assignment]
    user_id = get_current_user_id(token_payload)
    user = await _get_user(db, user_id)

    if user.mfa_enabled:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="mfa is already enabled",
        )

    if not user.mfa_secret:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="call /mfa/setup first",
        )

    totp = pyotp.TOTP(user.mfa_secret)
    if not totp.verify(body.code, valid_window=1):
        await _audit(
            db,
            user_id,
            "mfa_verify_failed",
        )
        await db.commit()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid totp code",
        )

    # generate recovery codes
    plaintext_codes = _generate_recovery_codes()
    hashed = [_hash_code(c) for c in plaintext_codes]
    user.recovery_codes = ",".join(hashed)
    user.mfa_enabled = True

    await _audit(db, user_id, "mfa_enabled")
    await db.commit()

    return MfaVerifyResponse(recovery_codes=plaintext_codes)


@router.post("/challenge", response_model=MfaChallengeResponse)
@limiter.limit("5/minute")
async def mfa_challenge(
    request: Request,
    body: MfaChallengeRequest,
    session: AsyncIterator[AsyncSession] = Depends(  # noqa: B008
        get_db_session
    ),
) -> MfaChallengeResponse:
    """complete mfa challenge with totp or recovery code."""
    db: AsyncSession = session  # type: ignore[assignment]

    try:
        payload = decode_token(body.challenge_token)
    except Exception as err:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid or expired challenge token",
        ) from err

    if payload.get("type") != "mfa_challenge":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid token type",
        )

    user_id = payload["sub"]
    user = await _get_user(db, user_id)

    if not user.mfa_enabled or not user.mfa_secret:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="mfa not enabled for this user",
        )

    # try totp first
    totp = pyotp.TOTP(user.mfa_secret)
    if totp.verify(body.code, valid_window=1):
        await _audit(
            db,
            str(user.id),
            "mfa_challenge_success",
        )
        await db.commit()
        return MfaChallengeResponse(
            access_token=create_access_token(str(user.id), user.role),
            refresh_token=create_refresh_token(str(user.id)),
        )

    # try recovery code
    code_hash = _hash_code(body.code)
    if user.recovery_codes:
        stored = user.recovery_codes.split(",")
        if code_hash in stored:
            stored.remove(code_hash)
            user.recovery_codes = ",".join(stored) if stored else None
            await _audit(
                db,
                str(user.id),
                "mfa_recovery_code_used",
                {"remaining": len(stored)},
            )
            await db.commit()
            return MfaChallengeResponse(
                access_token=create_access_token(str(user.id), user.role),
                refresh_token=create_refresh_token(str(user.id)),
            )

    await _audit(db, str(user.id), "mfa_challenge_failed")
    await db.commit()
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="invalid totp or recovery code",
    )


@router.delete(
    "",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def mfa_disable(
    body: MfaDisableRequest,
    token_payload: dict[str, Any] = Depends(  # noqa: B008
        require_authenticated
    ),
    session: AsyncIterator[AsyncSession] = Depends(  # noqa: B008
        get_db_session
    ),
) -> None:
    """disable mfa (requires current totp code)."""
    db: AsyncSession = session  # type: ignore[assignment]
    user_id = get_current_user_id(token_payload)
    user = await _get_user(db, user_id)

    if not user.mfa_enabled or not user.mfa_secret:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="mfa is not enabled",
        )

    totp = pyotp.TOTP(user.mfa_secret)
    if not totp.verify(body.code, valid_window=1):
        await _audit(db, user_id, "mfa_disable_failed")
        await db.commit()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid totp code",
        )

    user.mfa_enabled = False
    user.mfa_secret = None
    user.recovery_codes = None

    await _audit(db, user_id, "mfa_disabled")
    await db.commit()
