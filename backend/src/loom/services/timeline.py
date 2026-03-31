from collections import defaultdict
from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from loom.models.timeline import (
    TimelineEvent,
    TimelineEventEvidence,
)


async def create_event(
    session: AsyncSession,
    case_id: str,
    data: dict[str, Any],
    user_id: str,
) -> TimelineEvent:
    """create a timeline event."""
    event = TimelineEvent(
        case_id=UUID(case_id),
        title=data["title"],
        description=data.get("description"),
        event_time_start=data["event_time_start"],
        event_time_end=data.get("event_time_end"),
        time_precision=data.get("time_precision", "approximate"),
        location_description=data.get("location_description"),
        location_lat=data.get("location_lat"),
        location_lon=data.get("location_lon"),
        location_confidence=data.get("location_confidence", "unknown"),
        status=data.get("status", "draft"),
        created_by=UUID(user_id),
    )
    session.add(event)
    await session.commit()
    await session.refresh(event)
    return event


async def list_events(
    session: AsyncSession,
    case_id: str,
    status: str | None = None,
    skip: int = 0,
    limit: int = 50,
) -> tuple[list[TimelineEvent], int]:
    """list events with evidence_count and has_contradictions."""
    # subquery for evidence count
    evidence_count_sq = (
        select(func.count(TimelineEventEvidence.id))
        .where(TimelineEventEvidence.event_id == TimelineEvent.id)
        .correlate(TimelineEvent)
        .scalar_subquery()
        .label("evidence_count")
    )

    # subquery for supports count
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

    # subquery for contradicts count
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

    query = select(
        TimelineEvent,
        evidence_count_sq,
        supports_sq,
        contradicts_sq,
    ).where(TimelineEvent.case_id == UUID(case_id))

    if status is not None:
        query = query.where(TimelineEvent.status == status)

    # total count
    count_query = select(func.count()).select_from(
        query.with_only_columns(TimelineEvent.id).subquery()
    )
    total_result = await session.execute(count_query)
    total = total_result.scalar_one()

    # paginated results ordered by event_time_start
    query = query.order_by(TimelineEvent.event_time_start.asc())
    query = query.offset(skip).limit(limit)
    result = await session.execute(query)
    rows = result.all()

    events = []
    for row in rows:
        event = row[0]
        event.evidence_count = row[1] or 0
        supports = row[2] or 0
        contradicts = row[3] or 0
        event.has_contradictions = supports > 0 and contradicts > 0
        events.append(event)

    return events, total


async def get_event(
    session: AsyncSession,
    event_id: str,
) -> TimelineEvent | None:
    """get a single event by id."""
    # subqueries for counts
    evidence_count_sq = (
        select(func.count(TimelineEventEvidence.id))
        .where(TimelineEventEvidence.event_id == TimelineEvent.id)
        .correlate(TimelineEvent)
        .scalar_subquery()
        .label("evidence_count")
    )
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

    result = await session.execute(
        select(
            TimelineEvent,
            evidence_count_sq,
            supports_sq,
            contradicts_sq,
        ).where(TimelineEvent.id == UUID(event_id))
    )
    row = result.one_or_none()
    if row is None:
        return None

    event = row[0]
    event.evidence_count = row[1] or 0
    supports = row[2] or 0
    contradicts = row[3] or 0
    event.has_contradictions = supports > 0 and contradicts > 0
    return event  # type: ignore[no-any-return]


_UPDATABLE_EVENT_FIELDS: frozenset[str] = frozenset(
    {
        "title",
        "description",
        "event_time_start",
        "event_time_end",
        "time_precision",
        "location_description",
        "location_lat",
        "location_lon",
        "location_confidence",
        "status",
    }
)


async def update_event(
    session: AsyncSession,
    event_id: str,
    data: dict[str, Any],
) -> TimelineEvent:
    """update event fields."""
    result = await session.execute(
        select(TimelineEvent).where(TimelineEvent.id == UUID(event_id))
    )
    event = result.scalar_one()

    for key, value in data.items():
        if value is not None:
            if key not in _UPDATABLE_EVENT_FIELDS:
                raise ValueError(f"field '{key}' is not updatable")
            setattr(event, key, value)

    await session.commit()
    await session.refresh(event)

    # re-fetch with counts
    updated = await get_event(session, event_id)
    assert updated is not None  # just committed, must exist
    return updated


async def link_evidence(
    session: AsyncSession,
    event_id: str,
    data: dict[str, Any],
    user_id: str,
) -> TimelineEventEvidence:
    """link evidence to an event."""
    link = TimelineEventEvidence(
        event_id=UUID(event_id),
        asset_id=(UUID(data["asset_id"]) if data.get("asset_id") else None),
        annotation_id=(
            UUID(data["annotation_id"]) if data.get("annotation_id") else None
        ),
        derivative_id=(
            UUID(data["derivative_id"]) if data.get("derivative_id") else None
        ),
        clip_start=data.get("clip_start"),
        clip_end=data.get("clip_end"),
        relationship=data["relationship"],
        notes=data.get("notes"),
        linked_by=UUID(user_id),
    )
    session.add(link)
    await session.commit()
    await session.refresh(link)
    return link


async def unlink_evidence(
    session: AsyncSession,
    link_id: str,
) -> bool:
    """remove an evidence link."""
    result = await session.execute(
        select(TimelineEventEvidence).where(
            TimelineEventEvidence.id == UUID(link_id)
        )
    )
    link = result.scalar_one_or_none()
    if not link:
        return False

    await session.delete(link)
    await session.commit()
    return True


async def get_event_evidence(
    session: AsyncSession,
    event_id: str,
) -> list[TimelineEventEvidence]:
    """get all evidence links for an event."""
    result = await session.execute(
        select(TimelineEventEvidence)
        .where(TimelineEventEvidence.event_id == UUID(event_id))
        .order_by(TimelineEventEvidence.linked_at.asc())
    )
    return list(result.scalars().all())


async def get_timeline(
    session: AsyncSession,
    case_id: str,
    status: str | None = None,
) -> list[TimelineEvent]:
    """full timeline with events and their evidence links."""
    events, _ = await list_events(
        session, case_id, status=status, skip=0, limit=10000
    )

    if not events:
        return events

    # batch-fetch all evidence in one query instead of n+1
    event_ids = [event.id for event in events]
    result = await session.execute(
        select(TimelineEventEvidence)
        .where(TimelineEventEvidence.event_id.in_(event_ids))
        .order_by(TimelineEventEvidence.linked_at.asc())
    )
    all_evidence = list(result.scalars().all())

    # group by event_id
    evidence_by_event: dict[UUID, list[TimelineEventEvidence]] = defaultdict(
        list
    )
    for ev in all_evidence:
        evidence_by_event[ev.event_id].append(ev)

    for event in events:
        event.evidence = evidence_by_event.get(  # type: ignore[attr-defined]
            event.id, []
        )

    return events
