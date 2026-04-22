"""first-run onboarding endpoints.

These endpoints intentionally require NO authentication: they run
before any user exists on the deploy (fresh Loom Desktop Lite
install or empty server). Both endpoints guard against replay by
checking the users table — /status is informational and /complete
returns 409 Conflict once any user exists. See GitHub issue #42.
"""

from collections.abc import AsyncIterator

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from loom.config import get_settings
from loom.dependencies import get_db_session
from loom.models.user import User
from loom.schemas.first_run import (
    FirstRunCompleteRequest,
    FirstRunCompleteResponse,
    FirstRunStatus,
)
from loom.security.auth import (
    create_access_token,
    create_refresh_token,
    hash_password,
)
from loom.security.rate_limit import limiter

router = APIRouter(prefix="/first-run", tags=["first-run"])


async def _user_count(db: AsyncSession) -> int:
    """return total number of users in the database."""
    result = await db.execute(select(func.count()).select_from(User))
    return int(result.scalar_one())


@router.get("/status", response_model=FirstRunStatus)
async def get_status(
    session: AsyncIterator[AsyncSession] = Depends(  # noqa: B008
        get_db_session
    ),
) -> FirstRunStatus:
    """report whether first-run onboarding is required.

    no auth required by design: the caller is the desktop shell
    (or a fresh browser) before any user account exists.
    """
    db: AsyncSession = session  # type: ignore[assignment]
    settings = get_settings()

    count = await _user_count(db)
    data_dir = str(settings.resolved_data_dir()) if settings.is_lite else None
    return FirstRunStatus(
        first_run_required=(count == 0),
        deployment_profile=settings.deployment_profile,
        data_dir=data_dir,
    )


@router.post(
    "/complete",
    response_model=FirstRunCompleteResponse,
    status_code=status.HTTP_201_CREATED,
)
@limiter.limit("3/minute")
async def complete(
    request: Request,
    body: FirstRunCompleteRequest,
    session: AsyncIterator[AsyncSession] = Depends(  # noqa: B008
        get_db_session
    ),
) -> FirstRunCompleteResponse:
    """create the bootstrap admin user and return a token pair.

    no auth required by design. returns 409 Conflict if any user
    already exists — never silently overwrites an existing admin.
    """
    db: AsyncSession = session  # type: ignore[assignment]

    # guard: only allowed when the users table is empty
    count = await _user_count(db)
    if count > 0:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="first-run already completed",
        )

    user = User(
        email=body.admin_email,
        display_name=body.admin_full_name,
        password_hash=hash_password(body.admin_password),
        role="admin",
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)

    access = create_access_token(str(user.id), user.role)
    refresh = create_refresh_token(str(user.id))

    return FirstRunCompleteResponse(
        user_id=user.id,
        access_token=access,
        refresh_token=refresh,
    )
