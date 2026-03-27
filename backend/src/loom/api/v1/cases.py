from collections.abc import AsyncIterator
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from loom.dependencies import get_db_session
from loom.schemas.case import (
    CaseCreate,
    CaseListResponse,
    CaseMemberCreate,
    CaseMemberResponse,
    CaseResponse,
    CaseUpdate,
)
from loom.security.rbac import get_current_user_id, require_authenticated
from loom.services.case import (
    add_member,
    check_case_access,
    create_case,
    get_case,
    list_cases,
    list_members,
    remove_member,
    update_case,
)

router = APIRouter(prefix="/cases", tags=["cases"])


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
    return CaseResponse(
        id=case.id,
        name=case.name,
        description=case.description,
        status=case.status,
        created_by=case.created_by,
        created_at=case.created_at,
        updated_at=case.updated_at,
        asset_count=0,
        event_count=0,
    )


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
        CaseResponse(
            id=c.id,
            name=c.name,
            description=c.description,
            status=c.status,
            created_by=c.created_by,
            created_at=c.created_at,
            updated_at=c.updated_at,
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

    return CaseResponse(
        id=case.id,
        name=case.name,
        description=case.description,
        status=case.status,
        created_by=case.created_by,
        created_at=case.created_at,
        updated_at=case.updated_at,
    )


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
    return CaseResponse(
        id=case.id,
        name=case.name,
        description=case.description,
        status=case.status,
        created_by=case.created_by,
        created_at=case.created_at,
        updated_at=case.updated_at,
    )


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
    # fetch user email
    from sqlalchemy import select

    from loom.models.user import User

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
            user_email=m.user_email,  # type: ignore[attr-defined]
            role=m.role,
            granted_at=m.granted_at,
        )
        for m in members
    ]
