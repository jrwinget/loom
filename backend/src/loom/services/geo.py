from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from loom.models.asset import Asset
from loom.models.timeline import (
    TimelineEvent,
    TimelineEventEvidence,
)


async def get_geotagged_assets(
    session: AsyncSession,
    case_id: str,
    time_start: datetime | None = None,
    time_end: datetime | None = None,
) -> list[dict[str, Any]]:
    """query assets with non-null coordinates for a case."""
    query = (
        select(Asset)
        .where(
            Asset.case_id == UUID(case_id),
            Asset.capture_location_lat.isnot(None),
            Asset.capture_location_lon.isnot(None),
        )
        .order_by(Asset.capture_time.asc())
    )

    if time_start is not None:
        query = query.where(Asset.capture_time >= time_start)
    if time_end is not None:
        query = query.where(Asset.capture_time <= time_end)

    result = await session.execute(query)
    assets = result.scalars().all()

    return [
        {
            "id": str(a.id),
            "original_filename": a.original_filename,
            "media_type": a.media_type,
            "lat": a.capture_location_lat,
            "lon": a.capture_location_lon,
            "capture_time": a.capture_time,
        }
        for a in assets
    ]


async def get_geotagged_events(
    session: AsyncSession,
    case_id: str,
    time_start: datetime | None = None,
    time_end: datetime | None = None,
) -> list[dict[str, Any]]:
    """query timeline events with non-null coordinates."""
    # subquery to detect contradictions
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

    query = (
        select(TimelineEvent, supports_sq, contradicts_sq)
        .where(
            TimelineEvent.case_id == UUID(case_id),
            TimelineEvent.location_lat.isnot(None),
            TimelineEvent.location_lon.isnot(None),
        )
        .order_by(TimelineEvent.event_time_start.asc())
    )

    if time_start is not None:
        query = query.where(TimelineEvent.event_time_start >= time_start)
    if time_end is not None:
        query = query.where(TimelineEvent.event_time_start <= time_end)

    result = await session.execute(query)
    rows = result.all()

    return [
        {
            "id": str(row[0].id),
            "title": row[0].title,
            "status": row[0].status,
            "lat": row[0].location_lat,
            "lon": row[0].location_lon,
            "event_time_start": row[0].event_time_start,
            "has_contradictions": ((row[1] or 0) > 0 and (row[2] or 0) > 0),
        }
        for row in rows
    ]


async def get_geo_bounds(
    session: AsyncSession,
    case_id: str,
) -> dict[str, Any] | None:
    """compute bounding box across all geotagged items."""
    cid = UUID(case_id)

    # asset bounds
    asset_q = select(
        func.min(Asset.capture_location_lat),
        func.max(Asset.capture_location_lat),
        func.min(Asset.capture_location_lon),
        func.max(Asset.capture_location_lon),
        func.min(Asset.capture_time),
        func.max(Asset.capture_time),
    ).where(
        Asset.case_id == cid,
        Asset.capture_location_lat.isnot(None),
    )
    asset_result = await session.execute(asset_q)
    a_row = asset_result.one()

    # event bounds
    event_q = select(
        func.min(TimelineEvent.location_lat),
        func.max(TimelineEvent.location_lat),
        func.min(TimelineEvent.location_lon),
        func.max(TimelineEvent.location_lon),
        func.min(TimelineEvent.event_time_start),
        func.max(TimelineEvent.event_time_start),
    ).where(
        TimelineEvent.case_id == cid,
        TimelineEvent.location_lat.isnot(None),
    )
    event_result = await session.execute(event_q)
    e_row = event_result.one()

    # merge bounds from both sources
    lats = [v for v in [a_row[0], a_row[1], e_row[0], e_row[1]] if v]
    lons = [v for v in [a_row[2], a_row[3], e_row[2], e_row[3]] if v]
    times = [v for v in [a_row[4], a_row[5], e_row[4], e_row[5]] if v]

    if not lats:
        return None

    return {
        "min_lat": min(lats),
        "max_lat": max(lats),
        "min_lon": min(lons),
        "max_lon": max(lons),
        "time_start": min(times) if times else None,
        "time_end": max(times) if times else None,
    }
