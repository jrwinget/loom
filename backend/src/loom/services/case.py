from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from loom.models.asset import Asset
from loom.models.case import Case, CaseMembership
from loom.models.timeline import TimelineEvent
from loom.models.user import User


async def create_case(
    session: AsyncSession,
    name: str,
    description: str | None,
    user_id: str,
) -> Case:
    """create a case and add the creator as owner."""
    case = Case(
        name=name,
        description=description,
        created_by=user_id,
    )
    session.add(case)
    await session.flush()

    membership = CaseMembership(
        case_id=case.id,
        user_id=user_id,
        role="owner",
        granted_by=user_id,
    )
    session.add(membership)
    await session.commit()
    await session.refresh(case)
    return case


async def list_cases(
    session: AsyncSession,
    user_id: str,
    role: str,
    skip: int = 0,
    limit: int = 20,
) -> tuple[list, int]:
    """list cases with asset/event counts.

    admins see all cases; others see only their memberships.
    """
    # subqueries for counts
    asset_count_sq = (
        select(func.count(Asset.id))
        .where(Asset.case_id == Case.id)
        .correlate(Case)
        .scalar_subquery()
        .label("asset_count")
    )
    event_count_sq = (
        select(func.count(TimelineEvent.id))
        .where(TimelineEvent.case_id == Case.id)
        .correlate(Case)
        .scalar_subquery()
        .label("event_count")
    )

    query = select(Case, asset_count_sq, event_count_sq)

    if role != "admin":
        query = query.join(
            CaseMembership,
            CaseMembership.case_id == Case.id,
        ).where(CaseMembership.user_id == UUID(user_id))

    # total count
    count_query = select(func.count()).select_from(
        query.with_only_columns(Case.id).subquery()
    )
    total_result = await session.execute(count_query)
    total = total_result.scalar_one()

    # paginated results
    query = query.offset(skip).limit(limit)
    result = await session.execute(query)
    rows = result.all()

    cases = []
    for row in rows:
        case = row[0]
        case.asset_count = row[1] or 0
        case.event_count = row[2] or 0
        cases.append(case)

    return cases, total


async def get_case(
    session: AsyncSession,
    case_id: str,
) -> Case | None:
    """get a single case by id."""
    result = await session.execute(select(Case).where(Case.id == UUID(case_id)))
    return result.scalar_one_or_none()


async def update_case(
    session: AsyncSession,
    case_id: str,
    data: dict,
) -> Case:
    """update case fields."""
    result = await session.execute(select(Case).where(Case.id == UUID(case_id)))
    case = result.scalar_one()

    for key, value in data.items():
        if value is not None:
            setattr(case, key, value)

    await session.commit()
    await session.refresh(case)
    return case


_ROLE_HIERARCHY = {"viewer": 0, "editor": 1, "owner": 2}


async def check_case_access(
    session: AsyncSession,
    case_id: str,
    user_id: str,
    required_role: str = "viewer",
) -> bool:
    """check if user has required role on case (or is admin)."""
    # first check if user is admin
    user_result = await session.execute(
        select(User).where(User.id == UUID(user_id))
    )
    user = user_result.scalar_one_or_none()
    if user and user.role == "admin":
        return True

    result = await session.execute(
        select(CaseMembership).where(
            CaseMembership.case_id == UUID(case_id),
            CaseMembership.user_id == UUID(user_id),
        )
    )
    membership = result.scalar_one_or_none()
    if not membership:
        return False

    required_level = _ROLE_HIERARCHY.get(required_role, 0)
    user_level = _ROLE_HIERARCHY.get(membership.role, 0)
    return user_level >= required_level


async def add_member(
    session: AsyncSession,
    case_id: str,
    user_id: str,
    role: str,
    granted_by: str,
) -> CaseMembership:
    """add a member to a case."""
    membership = CaseMembership(
        case_id=UUID(case_id),
        user_id=UUID(user_id),
        role=role,
        granted_by=UUID(granted_by),
    )
    session.add(membership)
    await session.commit()
    await session.refresh(membership)
    return membership


async def remove_member(
    session: AsyncSession,
    case_id: str,
    user_id: str,
) -> bool:
    """remove a member from a case."""
    result = await session.execute(
        select(CaseMembership).where(
            CaseMembership.case_id == UUID(case_id),
            CaseMembership.user_id == UUID(user_id),
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
    case_id: str,
) -> list[CaseMembership]:
    """list all members of a case."""
    result = await session.execute(
        select(CaseMembership, User.email)
        .join(User, User.id == CaseMembership.user_id)
        .where(CaseMembership.case_id == UUID(case_id))
    )
    rows = result.all()
    members = []
    for row in rows:
        membership = row[0]
        membership.user_email = row[1]
        members.append(membership)
    return members
