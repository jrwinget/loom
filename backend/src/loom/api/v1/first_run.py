"""first-run onboarding endpoints.

These endpoints intentionally require NO authentication: they run
before any user exists on the deploy (fresh Loom Desktop Lite
install or empty server). Both endpoints guard against replay by
checking the users table — /status is informational and /complete
returns 409 Conflict once any user exists. See GitHub issue #42.
"""

from collections.abc import AsyncIterator

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import exists, func, insert, literal, select
from sqlalchemy.ext.asyncio import AsyncSession

from loom.config import get_settings
from loom.dependencies import get_db_session
from loom.models.audit import AuditLogEntry
from loom.models.base import _generate_uuid7
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
from loom.security.password_recovery import generate_codes as gen_codes
from loom.security.password_recovery import hash_code as hash_rec_code
from loom.security.password_recovery import serialize as ser_codes
from loom.security.rate_limit import limiter

router = APIRouter(prefix="/first-run", tags=["first-run"])


async def _user_count(db: AsyncSession) -> int:
    """return total number of users in the database."""
    result = await db.execute(select(func.count()).select_from(User))
    return int(result.scalar_one())


@router.get("/status", response_model=FirstRunStatus)
@limiter.limit("30/minute")
async def get_status(
    request: Request,
    session: AsyncIterator[AsyncSession] = Depends(  # noqa: B008
        get_db_session
    ),
) -> FirstRunStatus:
    """report whether first-run onboarding is required.

    no auth required by design: the caller is the desktop shell
    (or a fresh browser) before any user account exists. rate
    limited so the unauthenticated endpoint cannot be used to
    probe server-profile instances for enumeration.
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

    the insert is a single INSERT...SELECT...WHERE NOT EXISTS so
    two racing requests cannot both end up creating an admin. the
    rowcount check tells the loser it lost.
    """
    db: AsyncSession = session  # type: ignore[assignment]

    new_id = _generate_uuid7()
    hashed = hash_password(body.admin_password)

    # mint single-use password-recovery codes. plaintext is returned
    # once in the response below; only the hashes are persisted, so a
    # code that isn't saved by the operator is unrecoverable.
    recovery_plaintext = gen_codes()
    recovery_serialized = ser_codes(
        [hash_rec_code(c) for c in recovery_plaintext]
    )

    # atomic "insert only if no user exists" — SQLite + Postgres
    # both evaluate the SELECT subquery and INSERT in the same
    # statement, closing the TOCTOU between count() and add().
    user_exists = select(literal(1)).select_from(User).exists()
    src = select(
        literal(new_id).label("id"),
        literal(body.admin_email).label("email"),
        literal(body.admin_full_name).label("display_name"),
        literal(hashed).label("password_hash"),
        literal("admin").label("role"),
        literal(True).label("is_active"),
        literal(False).label("mfa_enabled"),
        literal(recovery_serialized).label("password_recovery_codes"),
    ).where(~exists(user_exists))
    stmt = insert(User).from_select(
        [
            "id",
            "email",
            "display_name",
            "password_hash",
            "role",
            "is_active",
            "mfa_enabled",
            "password_recovery_codes",
        ],
        src,
    )
    result = await db.execute(stmt)
    # AsyncSession.execute returns Result; DML returns CursorResult
    # at runtime. use getattr so mypy stays happy without a cast.
    rows_inserted = int(getattr(result, "rowcount", 0) or 0)
    if rows_inserted == 0:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="first-run already completed",
        )

    # explicit audit entry for the bootstrap admin. the audit
    # middleware also logs the POST, but here we tie the action to
    # the created user_id so the tamper-evident record answers
    # "which user became the bootstrap admin?".
    ip_address = request.client.host if request.client else None
    user_agent = request.headers.get("User-Agent")
    db.add(
        AuditLogEntry(
            actor_id=None,
            action="user.bootstrap.create",
            resource_type="users",
            resource_id=new_id,
            detail={"email": body.admin_email},
            ip_address=ip_address,
            user_agent=user_agent,
        )
    )

    await db.commit()

    access = create_access_token(str(new_id), "admin")
    refresh = create_refresh_token(str(new_id))

    return FirstRunCompleteResponse(
        user_id=new_id,
        access_token=access,
        refresh_token=refresh,
        password_recovery_codes=recovery_plaintext,
    )
