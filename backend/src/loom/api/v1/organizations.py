from collections.abc import AsyncIterator
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from loom.dependencies import get_db_session
from loom.models.user import User
from loom.schemas.organization import (
    OrgCreate,
    OrgListResponse,
    OrgMemberCreate,
    OrgMemberResponse,
    OrgResponse,
    OrgUpdate,
)
from loom.security.rbac import get_current_user_id, require_authenticated
from loom.services.organization import (
    add_member,
    check_org_admin,
    check_org_member,
    create_org,
    get_org,
    list_members,
    list_orgs,
    remove_member,
    update_org,
)

router = APIRouter(
    prefix="/organizations",
    tags=["organizations"],
)


@router.post(
    "",
    response_model=OrgResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_org_endpoint(
    body: OrgCreate,
    token_payload: dict[str, Any] = Depends(  # noqa: B008
        require_authenticated
    ),
    session: AsyncIterator[AsyncSession] = Depends(  # noqa: B008
        get_db_session
    ),
) -> OrgResponse:
    """create a new organization."""
    db: AsyncSession = session  # type: ignore[assignment]
    user_id = get_current_user_id(token_payload)

    org = await create_org(db, body.name, body.description, user_id)
    return OrgResponse(
        id=org.id,
        name=org.name,
        description=org.description,
        is_active=org.is_active,
        member_count=1,
        created_at=org.created_at,
    )


@router.get("", response_model=OrgListResponse)
async def list_orgs_endpoint(
    token_payload: dict[str, Any] = Depends(  # noqa: B008
        require_authenticated
    ),
    session: AsyncIterator[AsyncSession] = Depends(  # noqa: B008
        get_db_session
    ),
) -> OrgListResponse:
    """list organizations user belongs to."""
    db: AsyncSession = session  # type: ignore[assignment]
    user_id = get_current_user_id(token_payload)
    role = token_payload.get("role", "analyst")

    orgs, total = await list_orgs(db, user_id, role)
    items = [
        OrgResponse(
            id=o.id,
            name=o.name,
            description=o.description,
            is_active=o.is_active,
            member_count=getattr(o, "member_count", 0),
            created_at=o.created_at,
        )
        for o in orgs
    ]
    return OrgListResponse(items=items, total=total)


@router.get("/{org_id}", response_model=OrgResponse)
async def get_org_endpoint(
    org_id: str,
    token_payload: dict[str, Any] = Depends(  # noqa: B008
        require_authenticated
    ),
    session: AsyncIterator[AsyncSession] = Depends(  # noqa: B008
        get_db_session
    ),
) -> OrgResponse:
    """get organization detail."""
    db: AsyncSession = session  # type: ignore[assignment]
    user_id = get_current_user_id(token_payload)

    org = await get_org(db, org_id)
    if not org:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="organization not found",
        )

    is_member = await check_org_member(db, org_id, user_id)
    if not is_member:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="org membership required",
        )

    return OrgResponse(
        id=org.id,
        name=org.name,
        description=org.description,
        is_active=org.is_active,
        created_at=org.created_at,
    )


@router.patch("/{org_id}", response_model=OrgResponse)
async def update_org_endpoint(
    org_id: str,
    body: OrgUpdate,
    token_payload: dict[str, Any] = Depends(  # noqa: B008
        require_authenticated
    ),
    session: AsyncIterator[AsyncSession] = Depends(  # noqa: B008
        get_db_session
    ),
) -> OrgResponse:
    """update organization (org admin only)."""
    db: AsyncSession = session  # type: ignore[assignment]
    user_id = get_current_user_id(token_payload)

    is_admin = await check_org_admin(db, org_id, user_id)
    if not is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="org admin required",
        )

    data = body.model_dump(exclude_unset=True)
    org = await update_org(db, org_id, data)
    return OrgResponse(
        id=org.id,
        name=org.name,
        description=org.description,
        is_active=org.is_active,
        created_at=org.created_at,
    )


@router.post(
    "/{org_id}/members",
    response_model=OrgMemberResponse,
    status_code=status.HTTP_201_CREATED,
)
async def add_member_endpoint(
    org_id: str,
    body: OrgMemberCreate,
    token_payload: dict[str, Any] = Depends(  # noqa: B008
        require_authenticated
    ),
    session: AsyncIterator[AsyncSession] = Depends(  # noqa: B008
        get_db_session
    ),
) -> OrgMemberResponse:
    """add a member to an organization (org admin)."""
    db: AsyncSession = session  # type: ignore[assignment]
    user_id = get_current_user_id(token_payload)

    is_admin = await check_org_admin(db, org_id, user_id)
    if not is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="org admin required",
        )

    membership = await add_member(db, org_id, body.user_id, body.role)

    result = await db.execute(select(User).where(User.id == membership.user_id))
    user = result.scalar_one()

    return OrgMemberResponse(
        id=membership.id,
        user_id=membership.user_id,
        user_email=user.email,
        role=membership.role,
        joined_at=membership.joined_at,
    )


@router.delete(
    "/{org_id}/members/{member_user_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def remove_member_endpoint(
    org_id: str,
    member_user_id: str,
    token_payload: dict[str, Any] = Depends(  # noqa: B008
        require_authenticated
    ),
    session: AsyncIterator[AsyncSession] = Depends(  # noqa: B008
        get_db_session
    ),
) -> None:
    """remove a member from an organization (org admin)."""
    db: AsyncSession = session  # type: ignore[assignment]
    user_id = get_current_user_id(token_payload)

    is_admin = await check_org_admin(db, org_id, user_id)
    if not is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="org admin required",
        )

    removed = await remove_member(db, org_id, member_user_id)
    if not removed:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="membership not found",
        )


@router.get(
    "/{org_id}/members",
    response_model=list[OrgMemberResponse],
)
async def list_members_endpoint(
    org_id: str,
    token_payload: dict[str, Any] = Depends(  # noqa: B008
        require_authenticated
    ),
    session: AsyncIterator[AsyncSession] = Depends(  # noqa: B008
        get_db_session
    ),
) -> list[OrgMemberResponse]:
    """list organization members."""
    db: AsyncSession = session  # type: ignore[assignment]
    user_id = get_current_user_id(token_payload)

    is_member = await check_org_member(db, org_id, user_id)
    if not is_member:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="org membership required",
        )

    members = await list_members(db, org_id)
    return [
        OrgMemberResponse(
            id=m.id,
            user_id=m.user_id,
            user_email=getattr(m, "user_email", ""),
            role=m.role,
            joined_at=m.joined_at,
        )
        for m in members
    ]
