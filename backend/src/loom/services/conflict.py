from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from loom.models.asset import Asset
from loom.models.conflict import ConflictResolution
from loom.models.timeline import (
    TimelineEvent,
    TimelineEventEvidence,
)


async def get_event_conflicts(
    session: AsyncSession,
    event_id: str,
    case_id: str,
) -> dict[str, Any] | None:
    """get conflict detail for an event.

    returns none if event does not belong to case (idor guard).
    """
    # verify event belongs to case
    result = await session.execute(
        select(TimelineEvent).where(
            TimelineEvent.id == UUID(event_id),
            TimelineEvent.case_id == UUID(case_id),
        )
    )
    event = result.scalar_one_or_none()
    if event is None:
        return None

    # fetch evidence with optional asset join for filename
    evidence_result = await session.execute(
        select(
            TimelineEventEvidence,
            Asset.original_filename,
        )
        .outerjoin(
            Asset,
            TimelineEventEvidence.asset_id == Asset.id,
        )
        .where(TimelineEventEvidence.event_id == UUID(event_id))
        .order_by(TimelineEventEvidence.linked_at.asc())
    )
    rows = evidence_result.all()

    supporting: list[dict[str, Any]] = []
    contradicting: list[dict[str, Any]] = []
    for ev, filename in rows:
        detail = {
            "id": ev.id,
            "asset_id": ev.asset_id,
            "original_filename": filename,
            "annotation_id": ev.annotation_id,
            "clip_start": ev.clip_start,
            "clip_end": ev.clip_end,
            "relationship": ev.relationship,
            "notes": ev.notes,
        }
        if ev.relationship == "supports":
            supporting.append(detail)
        elif ev.relationship == "contradicts":
            contradicting.append(detail)

    # fetch resolutions
    res_result = await session.execute(
        select(ConflictResolution)
        .where(ConflictResolution.event_id == UUID(event_id))
        .order_by(ConflictResolution.created_at.asc())
    )
    resolutions = list(res_result.scalars().all())

    return {
        "event_id": event.id,
        "event_title": event.title,
        "supporting": supporting,
        "contradicting": contradicting,
        "resolutions": resolutions,
    }


async def list_case_conflicts(
    session: AsyncSession,
    case_id: str,
    resolved: bool | None = None,
    skip: int = 0,
    limit: int = 50,
) -> tuple[list[dict[str, Any]], int]:
    """list events that have both supports and contradicts."""
    # subqueries for counts
    supports_sq = (
        select(func.count(TimelineEventEvidence.id))
        .where(
            TimelineEventEvidence.event_id == TimelineEvent.id,
            TimelineEventEvidence.relationship == "supports",
        )
        .correlate(TimelineEvent)
        .scalar_subquery()
        .label("supports_count")
    )
    contradicts_sq = (
        select(func.count(TimelineEventEvidence.id))
        .where(
            TimelineEventEvidence.event_id == TimelineEvent.id,
            TimelineEventEvidence.relationship == "contradicts",
        )
        .correlate(TimelineEvent)
        .scalar_subquery()
        .label("contradicts_count")
    )
    resolution_sq = (
        select(func.count(ConflictResolution.id))
        .where(ConflictResolution.event_id == TimelineEvent.id)
        .correlate(TimelineEvent)
        .scalar_subquery()
        .label("resolution_count")
    )

    # base query: events in case with both supports + contradicts
    query = (
        select(
            TimelineEvent,
            supports_sq,
            contradicts_sq,
            resolution_sq,
        )
        .where(TimelineEvent.case_id == UUID(case_id))
        .having(supports_sq > 0)
        .having(contradicts_sq > 0)
        .group_by(TimelineEvent.id)
    )

    # filter by resolution status if requested
    if resolved is True:
        query = query.having(resolution_sq > 0)
    elif resolved is False:
        query = query.having(resolution_sq == 0)

    # total count
    count_query = select(func.count()).select_from(
        query.with_only_columns(TimelineEvent.id).subquery()
    )
    total_result = await session.execute(count_query)
    total = total_result.scalar_one()

    # paginated results
    query = query.order_by(TimelineEvent.event_time_start.asc())
    query = query.offset(skip).limit(limit)
    result = await session.execute(query)
    rows = result.all()

    items: list[dict[str, Any]] = []
    for row in rows:
        event = row[0]
        sup_count = row[1] or 0
        con_count = row[2] or 0
        res_count = row[3] or 0
        items.append(
            {
                "event_id": event.id,
                "event_title": event.title,
                "supporting_count": sup_count,
                "contradicting_count": con_count,
                "resolution_count": res_count,
                "is_resolved": res_count > 0,
            }
        )

    return items, total


async def create_resolution(
    session: AsyncSession,
    event_id: str,
    case_id: str,
    data: dict[str, Any],
    user_id: str,
) -> ConflictResolution:
    """create a conflict resolution record.

    verifies event belongs to case before creating.
    """
    # verify event belongs to case
    result = await session.execute(
        select(TimelineEvent).where(
            TimelineEvent.id == UUID(event_id),
            TimelineEvent.case_id == UUID(case_id),
        )
    )
    event = result.scalar_one_or_none()
    if event is None:
        raise ValueError("event not found in case")

    resolution = ConflictResolution(
        event_id=UUID(event_id),
        resolution_type=data["resolution_type"],
        notes=data.get("notes"),
        resolved_by=UUID(user_id),
    )
    session.add(resolution)
    await session.commit()
    await session.refresh(resolution)
    return resolution


async def update_resolution(
    session: AsyncSession,
    resolution_id: str,
    case_id: str,
    data: dict[str, Any],
) -> ConflictResolution | None:
    """update a conflict resolution.

    verifies resolution's event belongs to case (idor guard).
    """
    result = await session.execute(
        select(ConflictResolution).where(
            ConflictResolution.id == UUID(resolution_id)
        )
    )
    resolution = result.scalar_one_or_none()
    if resolution is None:
        return None

    # verify event belongs to case
    ev_result = await session.execute(
        select(TimelineEvent).where(
            TimelineEvent.id == resolution.event_id,
            TimelineEvent.case_id == UUID(case_id),
        )
    )
    if ev_result.scalar_one_or_none() is None:
        return None

    for key, value in data.items():
        if value is not None:
            setattr(resolution, key, value)

    await session.commit()
    await session.refresh(resolution)
    return resolution
