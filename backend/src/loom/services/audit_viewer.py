"""audit log viewer service.

provides filtered, paginated access to the append-only
audit log, plus summary statistics.
"""

from datetime import datetime
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from loom.models.audit import AuditLogEntry
from loom.schemas.audit import (
    ActionCount,
    ActorCount,
    AuditStatsResponse,
)


async def list_audit_entries(
    session: AsyncSession,
    *,
    actor_id: UUID | None = None,
    resource_type: str | None = None,
    action: str | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    case_id: str | None = None,
    skip: int = 0,
    limit: int = 20,
) -> tuple[list[AuditLogEntry], int]:
    """query audit log with filters, paginated.

    returns (entries, total_count).
    """
    query = select(AuditLogEntry)
    count_query = select(func.count(AuditLogEntry.id))

    # apply filters
    if actor_id is not None:
        query = query.where(AuditLogEntry.actor_id == actor_id)
        count_query = count_query.where(AuditLogEntry.actor_id == actor_id)

    if resource_type is not None:
        query = query.where(AuditLogEntry.resource_type == resource_type)
        count_query = count_query.where(
            AuditLogEntry.resource_type == resource_type
        )

    if action is not None:
        query = query.where(AuditLogEntry.action.contains(action))
        count_query = count_query.where(AuditLogEntry.action.contains(action))

    if date_from is not None:
        query = query.where(AuditLogEntry.timestamp >= date_from)
        count_query = count_query.where(AuditLogEntry.timestamp >= date_from)

    if date_to is not None:
        query = query.where(AuditLogEntry.timestamp <= date_to)
        count_query = count_query.where(AuditLogEntry.timestamp <= date_to)

    if case_id is not None:
        # filter by case_id in the action path
        pattern = f"%/cases/{case_id}%"
        query = query.where(AuditLogEntry.action.like(pattern))
        count_query = count_query.where(AuditLogEntry.action.like(pattern))

    # get total count
    total_result = await session.execute(count_query)
    total = total_result.scalar_one()

    # paginated, sorted by timestamp desc
    query = (
        query.order_by(AuditLogEntry.timestamp.desc()).offset(skip).limit(limit)
    )
    result = await session.execute(query)
    entries = list(result.scalars().all())

    return entries, total


async def get_audit_stats(
    session: AsyncSession,
    case_id: str | None = None,
) -> AuditStatsResponse:
    """compute summary statistics for the audit log.

    optionally scoped to a case via action path matching.
    """
    base_filter = []
    if case_id is not None:
        pattern = f"%/cases/{case_id}%"
        base_filter.append(AuditLogEntry.action.like(pattern))

    # total entries
    total_q = select(func.count(AuditLogEntry.id))
    for f in base_filter:
        total_q = total_q.where(f)
    total_result = await session.execute(total_q)
    total = total_result.scalar_one()

    # entries by action (extract method from "METHOD /path")
    # group by the full action string for now
    action_q = (
        select(
            AuditLogEntry.action,
            func.count(AuditLogEntry.id).label("cnt"),
        )
        .group_by(AuditLogEntry.action)
        .order_by(func.count(AuditLogEntry.id).desc())
        .limit(50)
    )
    for f in base_filter:
        action_q = action_q.where(f)
    action_result = await session.execute(action_q)
    by_action = [
        ActionCount(action=row[0], count=row[1]) for row in action_result.all()
    ]

    # entries by actor
    actor_q = (
        select(
            AuditLogEntry.actor_id,
            func.count(AuditLogEntry.id).label("cnt"),
        )
        .where(AuditLogEntry.actor_id.isnot(None))
        .group_by(AuditLogEntry.actor_id)
        .order_by(func.count(AuditLogEntry.id).desc())
        .limit(50)
    )
    for f in base_filter:
        actor_q = actor_q.where(f)
    actor_result = await session.execute(actor_q)
    by_actor = [
        ActorCount(actor_id=row[0], count=row[1]) for row in actor_result.all()
    ]

    # date range
    range_q = select(
        func.min(AuditLogEntry.timestamp),
        func.max(AuditLogEntry.timestamp),
    )
    for f in base_filter:
        range_q = range_q.where(f)
    range_result = await session.execute(range_q)
    range_row = range_result.one()

    return AuditStatsResponse(
        total_entries=total,
        by_action=by_action,
        by_actor=by_actor,
        earliest_entry=range_row[0],
        latest_entry=range_row[1],
    )
