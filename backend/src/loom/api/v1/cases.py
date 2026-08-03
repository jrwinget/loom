from collections.abc import AsyncIterator
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from loom.dependencies import get_db_session, get_storage_backend
from loom.models.case import Case
from loom.models.user import User
from loom.schemas.case import (
    CaseCreate,
    CaseHoldRequest,
    CaseListResponse,
    CaseMemberCreate,
    CaseMemberResponse,
    CasePurgeRequest,
    CaseResponse,
    CaseUpdate,
)
from loom.security.rbac import get_current_user_id, require_authenticated
from loom.services.case import (
    add_member,
    check_case_access,
    create_case,
    get_case,
    get_case_counts,
    list_cases,
    list_members,
    purge_case,
    release_case_hold,
    remove_member,
    set_case_hold,
    update_case,
)
from loom.services.storage_backends import StorageBackend

router = APIRouter(prefix="/cases", tags=["cases"])


def _case_response(
    case: Case,
    asset_count: int,
    event_count: int,
) -> CaseResponse:
    return CaseResponse(
        id=case.id,
        name=case.name,
        description=case.description,
        status=case.status,
        created_by=case.created_by,
        created_at=case.created_at,
        updated_at=case.updated_at,
        asset_count=asset_count,
        event_count=event_count,
        hold_active=case.hold_active,
        hold_reason=case.hold_reason,
        hold_set_by=case.hold_set_by,
        hold_set_at=case.hold_set_at,
    )


@router.post(
    "",
    response_model=CaseResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_case_endpoint(
    body: CaseCreate,
    token_payload: dict[str, Any] = Depends(  # noqa: B008
        require_authenticated
    ),
    session: AsyncIterator[AsyncSession] = Depends(  # noqa: B008
        get_db_session
    ),
) -> CaseResponse:
    """create a new case."""
    db: AsyncSession = session  # type: ignore[assignment]
    user_id = get_current_user_id(token_payload)

    case = await create_case(db, body.name, body.description, user_id)
    return _case_response(case, asset_count=0, event_count=0)


@router.get("", response_model=CaseListResponse)
async def list_cases_endpoint(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    token_payload: dict[str, Any] = Depends(  # noqa: B008
        require_authenticated
    ),
    session: AsyncIterator[AsyncSession] = Depends(  # noqa: B008
        get_db_session
    ),
) -> CaseListResponse:
    """list cases (filtered by membership)."""
    db: AsyncSession = session  # type: ignore[assignment]
    user_id = get_current_user_id(token_payload)
    role = token_payload.get("role", "analyst")

    cases, total = await list_cases(db, user_id, role, skip, limit)
    items = [
        _case_response(
            c,
            asset_count=getattr(c, "asset_count", 0),
            event_count=getattr(c, "event_count", 0),
        )
        for c in cases
    ]
    return CaseListResponse(items=items, total=total)


@router.get("/{case_id}", response_model=CaseResponse)
async def get_case_endpoint(
    case_id: str,
    token_payload: dict[str, Any] = Depends(  # noqa: B008
        require_authenticated
    ),
    session: AsyncIterator[AsyncSession] = Depends(  # noqa: B008
        get_db_session
    ),
) -> CaseResponse:
    """get case detail."""
    db: AsyncSession = session  # type: ignore[assignment]
    user_id = get_current_user_id(token_payload)

    has_access = await check_case_access(db, case_id, user_id)
    if not has_access:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="insufficient case access",
        )

    case = await get_case(db, case_id)
    if not case:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="case not found",
        )

    asset_count, event_count = await get_case_counts(db, case.id)
    return _case_response(case, asset_count, event_count)


@router.patch("/{case_id}", response_model=CaseResponse)
async def update_case_endpoint(
    case_id: str,
    body: CaseUpdate,
    token_payload: dict[str, Any] = Depends(  # noqa: B008
        require_authenticated
    ),
    session: AsyncIterator[AsyncSession] = Depends(  # noqa: B008
        get_db_session
    ),
) -> CaseResponse:
    """update case (requires editor+)."""
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

    data = body.model_dump(exclude_unset=True)
    case = await update_case(db, case_id, data)
    asset_count, event_count = await get_case_counts(db, case.id)
    return _case_response(case, asset_count, event_count)


@router.delete(
    "/{case_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def purge_case_endpoint(
    case_id: str,
    body: CasePurgeRequest,
    token_payload: dict[str, Any] = Depends(  # noqa: B008
        require_authenticated
    ),
    session: AsyncIterator[AsyncSession] = Depends(  # noqa: B008
        get_db_session
    ),
    storage: StorageBackend = Depends(  # noqa: B008
        get_storage_backend
    ),
) -> None:
    """permanently destroy a case and its evidence (owner only).

    the case must be closed or archived first (an explicit lifecycle
    step guards against destroying live work), the exact title must be
    confirmed, and a reason is required. an append-only audit tombstone
    is written before anything is deleted.
    """
    db: AsyncSession = session  # type: ignore[assignment]
    user_id = get_current_user_id(token_payload)

    has_access = await check_case_access(
        db, case_id, user_id, required_role="owner"
    )
    if not has_access:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="insufficient case access",
        )

    case = await get_case(db, case_id)
    if not case:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="case not found",
        )

    # checked before the lifecycle guard so the hold message wins:
    # a preservation lock outranks "close the case first"
    if case.hold_active:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="case is under litigation hold",
        )

    if case.status not in ("closed", "archived"):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="case must be closed or archived before it can be purged",
        )

    if body.confirm_title != case.name:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="confirm_title does not match the case title",
        )

    await purge_case(db, case, body.reason.strip(), user_id, storage)


async def _load_case_for_hold(
    db: AsyncSession,
    case_id: str,
    user_id: str,
) -> Case:
    has_access = await check_case_access(
        db, case_id, user_id, required_role="owner"
    )
    if not has_access:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="insufficient case access",
        )

    case = await get_case(db, case_id)
    if not case:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="case not found",
        )
    return case


@router.post("/{case_id}/hold", response_model=CaseResponse)
async def set_case_hold_endpoint(
    case_id: str,
    body: CaseHoldRequest,
    token_payload: dict[str, Any] = Depends(  # noqa: B008
        require_authenticated
    ),
    session: AsyncIterator[AsyncSession] = Depends(  # noqa: B008
        get_db_session
    ),
) -> CaseResponse:
    """place a litigation hold on a case (owner only).

    while held, purging the case and deleting its assets are refused —
    frcp 37(e) posture: evidence destruction must be impossible during
    pending or anticipated litigation. the hold and its audit entry
    land in the same commit.
    """
    db: AsyncSession = session  # type: ignore[assignment]
    user_id = get_current_user_id(token_payload)

    case = await _load_case_for_hold(db, case_id, user_id)
    if case.hold_active:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="case is already under litigation hold",
        )

    case = await set_case_hold(db, case, body.reason, user_id)
    asset_count, event_count = await get_case_counts(db, case.id)
    return _case_response(case, asset_count, event_count)


@router.post("/{case_id}/hold/release", response_model=CaseResponse)
async def release_case_hold_endpoint(
    case_id: str,
    body: CaseHoldRequest,
    token_payload: dict[str, Any] = Depends(  # noqa: B008
        require_authenticated
    ),
    session: AsyncIterator[AsyncSession] = Depends(  # noqa: B008
        get_db_session
    ),
) -> CaseResponse:
    """release a litigation hold (owner only).

    a reason is required and recorded in the audit trail; the case's
    hold fields are cleared in the same commit.
    """
    db: AsyncSession = session  # type: ignore[assignment]
    user_id = get_current_user_id(token_payload)

    case = await _load_case_for_hold(db, case_id, user_id)
    if not case.hold_active:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="case is not under litigation hold",
        )

    case = await release_case_hold(db, case, body.reason, user_id)
    asset_count, event_count = await get_case_counts(db, case.id)
    return _case_response(case, asset_count, event_count)


@router.post(
    "/{case_id}/members",
    response_model=CaseMemberResponse,
    status_code=status.HTTP_201_CREATED,
)
async def add_member_endpoint(
    case_id: str,
    body: CaseMemberCreate,
    token_payload: dict[str, Any] = Depends(  # noqa: B008
        require_authenticated
    ),
    session: AsyncIterator[AsyncSession] = Depends(  # noqa: B008
        get_db_session
    ),
) -> CaseMemberResponse:
    """add a member to a case (requires owner)."""
    db: AsyncSession = session  # type: ignore[assignment]
    user_id = get_current_user_id(token_payload)

    has_access = await check_case_access(
        db, case_id, user_id, required_role="owner"
    )
    if not has_access:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="insufficient case access",
        )

    membership = await add_member(db, case_id, body.user_id, body.role, user_id)
    result = await db.execute(select(User).where(User.id == membership.user_id))
    user = result.scalar_one()

    return CaseMemberResponse(
        id=membership.id,
        case_id=membership.case_id,
        user_id=membership.user_id,
        user_email=user.email,
        role=membership.role,
        granted_at=membership.granted_at,
    )


@router.delete(
    "/{case_id}/members/{member_user_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def remove_member_endpoint(
    case_id: str,
    member_user_id: str,
    token_payload: dict[str, Any] = Depends(  # noqa: B008
        require_authenticated
    ),
    session: AsyncIterator[AsyncSession] = Depends(  # noqa: B008
        get_db_session
    ),
) -> None:
    """remove a member from a case (requires owner)."""
    db: AsyncSession = session  # type: ignore[assignment]
    user_id = get_current_user_id(token_payload)

    has_access = await check_case_access(
        db, case_id, user_id, required_role="owner"
    )
    if not has_access:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="insufficient case access",
        )

    removed = await remove_member(db, case_id, member_user_id)
    if not removed:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="membership not found",
        )


@router.get(
    "/{case_id}/members",
    response_model=list[CaseMemberResponse],
)
async def list_members_endpoint(
    case_id: str,
    token_payload: dict[str, Any] = Depends(  # noqa: B008
        require_authenticated
    ),
    session: AsyncIterator[AsyncSession] = Depends(  # noqa: B008
        get_db_session
    ),
) -> list[CaseMemberResponse]:
    """list case members (requires case access)."""
    db: AsyncSession = session  # type: ignore[assignment]
    user_id = get_current_user_id(token_payload)

    has_access = await check_case_access(db, case_id, user_id)
    if not has_access:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="insufficient case access",
        )

    members = await list_members(db, case_id)
    return [
        CaseMemberResponse(
            id=m.id,
            case_id=m.case_id,
            user_id=m.user_id,
            user_email=getattr(m, "user_email", ""),
            role=m.role,
            granted_at=m.granted_at,
        )
        for m in members
    ]
