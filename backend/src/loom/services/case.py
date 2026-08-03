import asyncio
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from loom.models.asset import Asset
from loom.models.audit import AuditLogEntry
from loom.models.case import Case, CaseMembership
from loom.models.timeline import TimelineEvent
from loom.models.user import User
from loom.services.storage_backends.base import (
    ORIGINALS_BUCKET,
    StorageBackend,
)


async def create_case(
    session: AsyncSession,
    name: str,
    description: str | None,
    user_id: str,
) -> Case:
    """create a case and add the creator as owner.

    uses a savepoint so that case + membership are atomic;
    a failure adding the membership rolls back the case too.
    """
    async with session.begin_nested():
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
) -> tuple[list[Case], int]:
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


async def get_case_counts(
    session: AsyncSession,
    case_id: UUID,
) -> tuple[int, int]:
    """count a case's assets and timeline events."""
    asset_result = await session.execute(
        select(func.count(Asset.id)).where(Asset.case_id == case_id)
    )
    event_result = await session.execute(
        select(func.count(TimelineEvent.id)).where(
            TimelineEvent.case_id == case_id
        )
    )
    return asset_result.scalar_one(), event_result.scalar_one()


async def set_case_hold(
    session: AsyncSession,
    case: Case,
    reason: str,
    actor_id: str,
) -> Case:
    """place a litigation hold on a case.

    the audit entry lands in the same commit as the flag change so a
    held case can never exist without its record.
    """
    case.hold_active = True
    case.hold_reason = reason
    case.hold_set_by = UUID(actor_id)
    case.hold_set_at = datetime.now(UTC)
    session.add(
        AuditLogEntry(
            actor_id=actor_id,
            action="case_hold_set",
            resource_type="cases",
            resource_id=case.id,
            detail={"reason": reason},
        )
    )
    await session.commit()
    await session.refresh(case)
    return case


async def release_case_hold(
    session: AsyncSession,
    case: Case,
    reason: str,
    actor_id: str,
) -> Case:
    """release a litigation hold.

    the release reason is recorded only in the audit trail; the case's
    hold fields are cleared in the same commit.
    """
    case.hold_active = False
    case.hold_reason = None
    case.hold_set_by = None
    case.hold_set_at = None
    session.add(
        AuditLogEntry(
            actor_id=actor_id,
            action="case_hold_released",
            resource_type="cases",
            resource_id=case.id,
            detail={"reason": reason},
        )
    )
    await session.commit()
    await session.refresh(case)
    return case


_UPDATABLE_CASE_FIELDS: frozenset[str] = frozenset(
    {
        "name",
        "description",
        "status",
    }
)


async def update_case(
    session: AsyncSession,
    case_id: str,
    data: dict[str, Any],
) -> Case:
    """update case fields."""
    result = await session.execute(select(Case).where(Case.id == UUID(case_id)))
    case = result.scalar_one_or_none()
    if case is None:
        raise ValueError("case not found")

    for key, value in data.items():
        if value is not None:
            if key not in _UPDATABLE_CASE_FIELDS:
                raise ValueError(f"field '{key}' is not updatable")
            setattr(case, key, value)

    await session.commit()
    await session.refresh(case)
    return case


async def purge_case(
    session: AsyncSession,
    case: Case,
    reason: str,
    actor_id: str,
    storage: StorageBackend,
) -> None:
    """permanently destroy a case, its assets, and all case-scoped data.

    chain of custody is sacred: the append-only audit tombstone that
    records exactly what was destroyed (title, reason, each asset's id,
    filename, and sha256) is written and flushed *before* any row is
    removed and committed together with the deletion, so a destroyed
    case can never exist without its record. child rows drop via the
    on-delete cascade on the case foreign key.

    originals are removed from object storage only after that commit —
    deleting a file is irreversible and not transactional, so doing it
    last means a failure there leaves a reap-able orphan file rather
    than an original destroyed with no committed audit record.
    """
    result = await session.execute(
        select(Asset).where(Asset.case_id == case.id)
    )
    assets = list(result.scalars())
    storage_keys = [asset.storage_key for asset in assets]

    session.add(
        AuditLogEntry(
            actor_id=actor_id,
            action="case_purged",
            resource_type="cases",
            resource_id=case.id,
            detail={
                "title": case.name,
                "reason": reason,
                "asset_count": len(assets),
                "assets": [
                    {
                        "id": str(asset.id),
                        "original_filename": asset.original_filename,
                        "sha256": asset.sha256_hash,
                    }
                    for asset in assets
                ],
            },
        )
    )
    await session.flush()

    await session.delete(case)
    await session.commit()

    loop = asyncio.get_running_loop()
    for key in storage_keys:
        await loop.run_in_executor(
            None,
            storage.delete_object,
            ORIGINALS_BUCKET,
            key,
        )


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
