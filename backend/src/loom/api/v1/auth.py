from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from loom.dependencies import get_db_session
from loom.models.user import User
from loom.schemas.user import (
    TokenRefresh,
    TokenResponse,
    UserCreate,
    UserLogin,
    UserResponse,
)
from loom.security.auth import (
    create_access_token,
    create_mfa_challenge_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)
from loom.security.rate_limit import limiter
from loom.security.rbac import (
    get_current_user_id,
    require_authenticated,
    require_role,
)
from loom.services.token_revocation import revoke_token

router = APIRouter(prefix="/auth", tags=["auth"])

_admin_dep = require_role("admin")


@router.post(
    "/register",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
)
@limiter.limit("3/minute")
async def register(
    request: Request,
    body: UserCreate,
    session: AsyncIterator[AsyncSession] = Depends(  # noqa: B008
        get_db_session
    ),
) -> User:
    """register a new user."""
    db: AsyncSession = session  # type: ignore[assignment]

    # check if any users exist (first user becomes admin)
    count_result = await db.execute(select(func.count()).select_from(User))
    user_count = count_result.scalar_one()
    is_first_user = user_count == 0

    if not is_first_user:
        # require admin token for subsequent registrations
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="admin token required to register users",
        )

    # check for existing email
    existing = await db.execute(select(User).where(User.email == body.email))
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="email already registered",
        )

    user = User(
        email=body.email,
        display_name=body.display_name,
        password_hash=hash_password(body.password),
        role="admin" if is_first_user else "analyst",
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


@router.post(
    "/register-user",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
)
@limiter.limit("3/minute")
async def register_user(
    request: Request,
    body: UserCreate,
    token_payload: dict[str, Any] = Depends(  # noqa: B008
        _admin_dep
    ),
    session: AsyncIterator[AsyncSession] = Depends(  # noqa: B008
        get_db_session
    ),
) -> User:
    """register a new user (admin only)."""
    db: AsyncSession = session  # type: ignore[assignment]

    # check for existing email
    existing = await db.execute(select(User).where(User.email == body.email))
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="email already registered",
        )

    user = User(
        email=body.email,
        display_name=body.display_name,
        password_hash=hash_password(body.password),
        role="analyst",
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


@router.post("/login")
@limiter.limit("5/minute")
async def login(
    request: Request,
    body: UserLogin,
    session: AsyncIterator[AsyncSession] = Depends(  # noqa: B008
        get_db_session
    ),
) -> TokenResponse | dict[str, object]:
    """authenticate and return tokens (or mfa challenge)."""
    db: AsyncSession = session  # type: ignore[assignment]

    result = await db.execute(
        select(User).where(User.email == body.email)
    )
    user = result.scalar_one_or_none()

    if not user or not verify_password(
        body.password, user.password_hash
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid credentials",
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="account is disabled",
        )

    if user.mfa_enabled:
        challenge = create_mfa_challenge_token(str(user.id))
        return {
            "requires_mfa": True,
            "challenge_token": challenge,
        }

    return TokenResponse(
        access_token=create_access_token(
            str(user.id), user.role
        ),
        refresh_token=create_refresh_token(str(user.id)),
    )


@router.post("/refresh", response_model=TokenResponse)
async def refresh(
    body: TokenRefresh,
    request: Request,
    session: AsyncIterator[AsyncSession] = Depends(  # noqa: B008
        get_db_session
    ),
) -> TokenResponse:
    """refresh access token."""
    db: AsyncSession = session  # type: ignore[assignment]

    try:
        payload = decode_token(body.refresh_token)
    except Exception as err:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid or expired refresh token",
        ) from err

    if payload.get("type") != "refresh":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid token type",
        )

    # check if refresh token is revoked
    jti = payload.get("jti")
    if jti:
        from loom.services.token_revocation import (
            is_token_revoked,
        )

        try:
            if await is_token_revoked(db, jti):
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="refresh token has been revoked",
                )
        except HTTPException:
            raise
        except Exception:  # noqa: S110
            # allow refresh if revocation check fails
            pass

    user_id = payload["sub"]
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()

    if not user or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="user not found or inactive",
        )

    # revoke the old refresh token so it can't be reused
    if jti:
        exp = payload.get("exp")
        if exp:
            await revoke_token(
                db,
                jti,
                str(user.id),
                datetime.fromtimestamp(exp, tz=UTC),
            )

    return TokenResponse(
        access_token=create_access_token(str(user.id), user.role),
        refresh_token=create_refresh_token(str(user.id)),
    )


@router.post(
    "/logout",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def logout(
    request: Request,
    token_payload: dict[str, Any] = Depends(  # noqa: B008
        require_authenticated
    ),
    session: AsyncIterator[AsyncSession] = Depends(  # noqa: B008
        get_db_session
    ),
) -> None:
    """revoke the current access token."""
    db: AsyncSession = session  # type: ignore[assignment]

    jti = token_payload.get("jti")
    if not jti:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="token missing jti claim",
        )

    user_id = get_current_user_id(token_payload)
    exp = token_payload.get("exp")

    # default to 24h if no exp (shouldn't happen)
    if exp:
        expires_at = datetime.fromtimestamp(exp, tz=UTC)
    else:
        from datetime import timedelta

        expires_at = datetime.now(UTC) + timedelta(hours=24)

    await revoke_token(db, jti, user_id, expires_at)


@router.get("/me", response_model=UserResponse)
async def get_me(
    token_payload: dict[str, Any] = Depends(  # noqa: B008
        require_authenticated
    ),
    session: AsyncIterator[AsyncSession] = Depends(  # noqa: B008
        get_db_session
    ),
) -> User:
    """return the current authenticated user."""
    db: AsyncSession = session  # type: ignore[assignment]
    user_id = get_current_user_id(token_payload)

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="user not found",
        )
    return user
