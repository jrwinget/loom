"""audit log viewer api endpoints."""

from collections.abc import AsyncIterator
from datetime import datetime
from typing import Any
from uuid import UUID

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Query,
    status,
)
from sqlalchemy.ext.asyncio import AsyncSession

from loom.dependencies import get_db_session
from loom.schemas.audit import (
    AuditEntryListResponse,
    AuditEntryResponse,
    AuditStatsResponse,
)
from loom.security.rbac import (
    get_current_user_id,
    require_authenticated,
    require_role,
)
from loom.services.audit_viewer import (
    get_audit_stats,
    list_audit_entries,
)
from loom.services.case import check_case_access

router = APIRouter(tags=["audit"])


@router.get(
    "/audit",
    response_model=AuditEntryListResponse,
)
async def list_all_audit_entries(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    actor_id: UUID | None = Query(None),  # noqa: B008
    resource_type: str | None = Query(None),
    action: str | None = Query(None),
    date_from: datetime | None = Query(None),  # noqa: B008
    date_to: datetime | None = Query(None),  # noqa: B008
    token_payload: dict[str, Any] = Depends(  # noqa: B008
        require_role("admin")  # noqa: B008
    ),
    session: AsyncIterator[AsyncSession] = Depends(  # noqa: B008
        get_db_session
    ),
) -> AuditEntryListResponse:
    """list audit entries (admin only)."""
    db: AsyncSession = session  # type: ignore[assignment]

    entries, total = await list_audit_entries(
        db,
        actor_id=actor_id,
        resource_type=resource_type,
        action=action,
        date_from=date_from,
        date_to=date_to,
        skip=skip,
        limit=limit,
    )

    return AuditEntryListResponse(
        items=[AuditEntryResponse.model_validate(e) for e in entries],
        total=total,
    )


@router.get(
    "/audit/stats",
    response_model=AuditStatsResponse,
)
async def get_global_audit_stats(
    token_payload: dict[str, Any] = Depends(  # noqa: B008
        require_role("admin")  # noqa: B008
    ),
    session: AsyncIterator[AsyncSession] = Depends(  # noqa: B008
        get_db_session
    ),
) -> AuditStatsResponse:
    """get global audit statistics (admin only)."""
    db: AsyncSession = session  # type: ignore[assignment]
    return await get_audit_stats(db)


@router.get(
    "/cases/{case_id}/audit",
    response_model=AuditEntryListResponse,
)
async def list_case_audit_entries(
    case_id: str,
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    actor_id: UUID | None = Query(None),  # noqa: B008
    action: str | None = Query(None),
    date_from: datetime | None = Query(None),  # noqa: B008
    date_to: datetime | None = Query(None),  # noqa: B008
    token_payload: dict[str, Any] = Depends(  # noqa: B008
        require_authenticated
    ),
    session: AsyncIterator[AsyncSession] = Depends(  # noqa: B008
        get_db_session
    ),
) -> AuditEntryListResponse:
    """list audit entries for a case (editor+ role required)."""
    db: AsyncSession = session  # type: ignore[assignment]
    user_id = get_current_user_id(token_payload)

    has_access = await check_case_access(
        db, case_id, user_id, required_role="editor"
    )
    if not has_access:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="insufficient case access",
        )

    entries, total = await list_audit_entries(
        db,
        actor_id=actor_id,
        action=action,
        date_from=date_from,
        date_to=date_to,
        case_id=case_id,
        skip=skip,
        limit=limit,
    )

    return AuditEntryListResponse(
        items=[AuditEntryResponse.model_validate(e) for e in entries],
        total=total,
    )
