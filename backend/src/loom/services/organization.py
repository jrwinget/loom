from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from loom.models.organization import (
    Organization,
    OrganizationMembership,
)
from loom.models.user import User


async def create_org(
    session: AsyncSession,
    name: str,
    description: str | None,
    user_id: str,
) -> Organization:
    """create an organization and add creator as admin.

    uses a savepoint so that org + membership are atomic.
    """
    async with session.begin_nested():
        org = Organization(
            name=name,
            description=description,
        )
        session.add(org)
        await session.flush()

        membership = OrganizationMembership(
            org_id=org.id,
            user_id=UUID(user_id),
            role="admin",
        )
        session.add(membership)
    await session.commit()
    await session.refresh(org)
    return org


async def list_orgs(
    session: AsyncSession,
    user_id: str,
    role: str = "analyst",
) -> tuple[list[Organization], int]:
    """list orgs user belongs to (or all if system admin)."""
    member_count_sq = (
        select(func.count(OrganizationMembership.id))
        .where(
            OrganizationMembership.org_id == Organization.id,
        )
        .correlate(Organization)
        .scalar_subquery()
        .label("member_count")
    )

    query = select(Organization, member_count_sq)

    if role != "admin":
        query = query.join(
            OrganizationMembership,
            OrganizationMembership.org_id == Organization.id,
        ).where(
            OrganizationMembership.user_id == UUID(user_id),
        )

    count_query = select(func.count()).select_from(
        query.with_only_columns(Organization.id).subquery()
    )
    total_result = await session.execute(count_query)
    total = total_result.scalar_one()

    result = await session.execute(query)
    rows = result.all()

    orgs: list[Organization] = []
    for row in rows:
        org = row[0]
        org.member_count = row[1] or 0
        orgs.append(org)

    return orgs, total


async def get_org(
    session: AsyncSession,
    org_id: str,
) -> Organization | None:
    """get a single org by id."""
    result = await session.execute(
        select(Organization).where(
            Organization.id == UUID(org_id),
        )
    )
    return result.scalar_one_or_none()


async def update_org(
    session: AsyncSession,
    org_id: str,
    data: dict[str, Any],
) -> Organization:
    """update organization fields."""
    result = await session.execute(
        select(Organization).where(
            Organization.id == UUID(org_id),
        )
    )
    org = result.scalar_one()

    for key, value in data.items():
        if value is not None:
            setattr(org, key, value)

    await session.commit()
    await session.refresh(org)
    return org


async def add_member(
    session: AsyncSession,
    org_id: str,
    user_id: str,
    role: str = "member",
) -> OrganizationMembership:
    """add a member to an organization."""
    membership = OrganizationMembership(
        org_id=UUID(org_id),
        user_id=UUID(user_id),
        role=role,
    )
    session.add(membership)
    await session.commit()
    await session.refresh(membership)
    return membership


async def remove_member(
    session: AsyncSession,
    org_id: str,
    user_id: str,
) -> bool:
    """remove a member from an organization."""
    result = await session.execute(
        select(OrganizationMembership).where(
            OrganizationMembership.org_id == UUID(org_id),
            OrganizationMembership.user_id == UUID(user_id),
        )
    )
    membership = result.scalar_one_or_none()
    if not membership:
        return False

    await session.delete(membership)
    await session.commit()
    return True


async def list_members(
    session: AsyncSession,
    org_id: str,
) -> list[OrganizationMembership]:
    """list all members of an organization."""
    result = await session.execute(
        select(OrganizationMembership, User.email)
        .join(
            User,
            User.id == OrganizationMembership.user_id,
        )
        .where(
            OrganizationMembership.org_id == UUID(org_id),
        )
    )
    rows = result.all()
    members: list[OrganizationMembership] = []
    for row in rows:
        membership = row[0]
        membership.user_email = row[1]
        members.append(membership)
    return members


async def check_org_member(
    session: AsyncSession,
    org_id: str,
    user_id: str,
) -> bool:
    """verify user is a member of the org (any role) or system admin."""
    # check system admin
    user_result = await session.execute(
        select(User).where(User.id == UUID(user_id))
    )
    user = user_result.scalar_one_or_none()
    if user and user.role == "admin":
        return True

    result = await session.execute(
        select(OrganizationMembership).where(
            OrganizationMembership.org_id == UUID(org_id),
            OrganizationMembership.user_id == UUID(user_id),
        )
    )
    membership = result.scalar_one_or_none()
    return membership is not None


async def check_org_admin(
    session: AsyncSession,
    org_id: str,
    user_id: str,
) -> bool:
    """verify user is an org admin (or system admin)."""
    # check system admin
    user_result = await session.execute(
        select(User).where(User.id == UUID(user_id))
    )
    user = user_result.scalar_one_or_none()
    if user and user.role == "admin":
        return True

    result = await session.execute(
        select(OrganizationMembership).where(
            OrganizationMembership.org_id == UUID(org_id),
            OrganizationMembership.user_id == UUID(user_id),
        )
    )
    membership = result.scalar_one_or_none()
    if not membership:
        return False

    return membership.role == "admin"
