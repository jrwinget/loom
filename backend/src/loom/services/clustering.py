"""cross-source event clustering service.

groups temporally overlapping content from different assets
into proposed event clusters for human review.
"""

import logging
from datetime import datetime, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from loom.models.annotation import Annotation
from loom.models.asset import Asset
from loom.models.event_cluster import EventCluster, EventClusterItem
from loom.models.ocr import OcrRegion
from loom.models.timeline import TimelineEvent
from loom.models.transcript import TranscriptSegment
from loom.services.graph_utils import connected_components

logger = logging.getLogger(__name__)


async def compute_absolute_times(
    session: AsyncSession,
    case_id: str,
) -> list[dict[str, Any]]:
    """map relative content times to absolute times.

    queries assets with capture_time, then for each asset
    gathers transcript segments, ocr regions, and annotations
    with time ranges. returns flat list of dicts with
    absolute timestamps.
    """
    result = await session.execute(
        select(Asset).where(
            Asset.case_id == UUID(case_id),
            Asset.capture_time.isnot(None),
        )
    )
    assets = list(result.scalars().all())

    if not assets:
        return []

    items: list[dict[str, Any]] = []

    # transcript segments
    for asset in assets:
        seg_result = await session.execute(
            select(TranscriptSegment).where(
                TranscriptSegment.asset_id == asset.id,
            )
        )
        segments = seg_result.scalars().all()
        for seg in segments:
            ct = asset.capture_time
            assert ct is not None  # filtered above
            abs_start = ct + timedelta(seconds=seg.start_time)
            abs_end = ct + timedelta(seconds=seg.end_time)
            items.append(
                {
                    "asset_id": asset.id,
                    "content_type": "transcript",
                    "content_id": seg.id,
                    "absolute_time_start": abs_start,
                    "absolute_time_end": abs_end,
                    "text_preview": seg.text[:200],
                }
            )

    # ocr regions
    for asset in assets:
        ocr_result = await session.execute(
            select(OcrRegion).where(
                OcrRegion.asset_id == asset.id,
                OcrRegion.timestamp.isnot(None),
            )
        )
        regions = ocr_result.scalars().all()
        for region in regions:
            ct = asset.capture_time
            assert ct is not None
            ts = region.timestamp
            assert ts is not None  # filtered above
            abs_start = ct + timedelta(seconds=ts)
            items.append(
                {
                    "asset_id": asset.id,
                    "content_type": "ocr",
                    "content_id": region.id,
                    "absolute_time_start": abs_start,
                    "absolute_time_end": None,
                    "text_preview": region.text[:200],
                }
            )

    # annotations with time ranges
    for asset in assets:
        ann_result = await session.execute(
            select(Annotation).where(
                Annotation.asset_id == asset.id,
                Annotation.time_start.isnot(None),
            )
        )
        annotations = ann_result.scalars().all()
        for ann in annotations:
            ct = asset.capture_time
            assert ct is not None
            ts = ann.time_start
            assert ts is not None  # filtered above
            abs_start = ct + timedelta(seconds=ts)
            te = ann.time_end
            ann_end: datetime | None = (
                ct + timedelta(seconds=te) if te is not None else None
            )
            items.append(
                {
                    "asset_id": asset.id,
                    "content_type": "annotation",
                    "content_id": ann.id,
                    "absolute_time_start": abs_start,
                    "absolute_time_end": ann_end,
                    "text_preview": ann.content[:200],
                }
            )

    return items


def find_temporal_clusters(
    items: list[dict[str, Any]],
    window_seconds: int = 60,
) -> list[list[dict[str, Any]]]:
    """group items by temporal overlap across assets.

    pure function (no db). sorts by start time, connects
    items from different assets whose time windows overlap
    within the given window. uses union-find via
    connected_components. discards single-asset clusters.
    """
    if not items:
        return []

    # sort by absolute_time_start
    sorted_items = sorted(items, key=lambda x: x["absolute_time_start"])
    n = len(sorted_items)
    window = timedelta(seconds=window_seconds)

    # find pairs from different assets within window
    pairs: list[tuple[int, int]] = []
    for i in range(n):
        for j in range(i + 1, n):
            # if j start is beyond i's effective end, stop
            i_end = (
                sorted_items[i]["absolute_time_end"]
                or sorted_items[i]["absolute_time_start"]
            )
            effective_end = i_end + window
            if sorted_items[j]["absolute_time_start"] > effective_end:
                break

            # only connect items from different assets
            if sorted_items[i]["asset_id"] == sorted_items[j]["asset_id"]:
                continue

            pairs.append((i, j))

    if not pairs:
        return []

    components = connected_components(pairs, n)

    # filter: keep only clusters with items from 2+ assets
    result: list[list[dict[str, Any]]] = []
    for component in components:
        cluster_items = [sorted_items[idx] for idx in component]
        asset_ids = {item["asset_id"] for item in cluster_items}
        if len(asset_ids) >= 2:
            result.append(cluster_items)

    return result


async def propose_clusters(
    session: AsyncSession,
    case_id: str,
    window_seconds: int,
    user_id: str,
) -> list[EventCluster]:
    """compute and persist proposed event clusters."""
    items = await compute_absolute_times(session, case_id)
    clusters = find_temporal_clusters(items, window_seconds)

    if not clusters:
        return []

    # fetch asset filenames for title generation
    asset_result = await session.execute(
        select(Asset).where(Asset.case_id == UUID(case_id))
    )
    asset_map = {
        a.id: a.original_filename for a in asset_result.scalars().all()
    }

    persisted: list[EventCluster] = []
    for cluster_items in clusters:
        starts = [item["absolute_time_start"] for item in cluster_items]
        ends = [
            item["absolute_time_end"] or item["absolute_time_start"]
            for item in cluster_items
        ]
        time_start = min(starts)
        time_end = max(ends)

        # build a descriptive title from asset filenames
        asset_ids = {item["asset_id"] for item in cluster_items}
        names = [
            asset_map.get(aid, "unknown") for aid in sorted(asset_ids, key=str)
        ]
        title = f"Cross-source event: {', '.join(names[:3])}"
        if len(names) > 3:
            title += f" +{len(names) - 3} more"

        # savepoint: each cluster + items is atomic
        async with session.begin_nested():
            cluster = EventCluster(
                case_id=UUID(case_id),
                status="proposed",
                proposed_title=title,
                proposed_description=None,
                time_window_start=time_start,
                time_window_end=time_end,
            )
            session.add(cluster)
            await session.flush()

            for item in cluster_items:
                ci = EventClusterItem(
                    cluster_id=cluster.id,
                    asset_id=item["asset_id"],
                    content_type=item["content_type"],
                    content_id=item["content_id"],
                    absolute_time_start=item["absolute_time_start"],
                    absolute_time_end=item.get("absolute_time_end"),
                    text_preview=item["text_preview"],
                )
                session.add(ci)

        persisted.append(cluster)

    await session.commit()

    # reload with items
    result = []
    for cluster in persisted:
        loaded = await get_cluster(session, str(cluster.id), case_id)
        if loaded:
            result.append(loaded)
    return result


async def accept_cluster(
    session: AsyncSession,
    cluster_id: str,
    case_id: str,
    title: str,
    description: str | None,
    user_id: str,
) -> EventCluster:
    """accept a cluster, creating a timeline event.

    uses a savepoint so event creation + cluster update
    are atomic.
    """
    cluster = await _load_cluster(session, cluster_id, case_id)

    async with session.begin_nested():
        # create timeline event from cluster data
        event = TimelineEvent(
            case_id=UUID(case_id),
            title=title,
            description=description,
            event_time_start=cluster.time_window_start,
            event_time_end=cluster.time_window_end,
            time_precision="approximate",
            status="draft",
            created_by=UUID(user_id),
        )
        session.add(event)
        await session.flush()

        cluster.event_id = event.id
        cluster.status = "accepted"
        cluster.reviewed_by = UUID(user_id)
    await session.commit()
    await session.refresh(cluster)

    loaded = await get_cluster(session, str(cluster.id), case_id)
    assert loaded is not None
    return loaded


async def reject_cluster(
    session: AsyncSession,
    cluster_id: str,
    case_id: str,
    user_id: str,
) -> EventCluster:
    """reject a cluster."""
    cluster = await _load_cluster(session, cluster_id, case_id)
    cluster.status = "rejected"
    cluster.reviewed_by = UUID(user_id)
    await session.commit()
    await session.refresh(cluster)
    return cluster


async def merge_clusters(
    session: AsyncSession,
    cluster_ids: list[str],
    case_id: str,
    user_id: str,
) -> EventCluster:
    """merge multiple clusters into the first one."""
    clusters = []
    for cid in cluster_ids:
        c = await _load_cluster(session, cid, case_id)
        clusters.append(c)

    primary = clusters[0]

    async with session.begin_nested():
        for other in clusters[1:]:
            # move items to primary cluster
            items_result = await session.execute(
                select(EventClusterItem).where(
                    EventClusterItem.cluster_id == other.id,
                )
            )
            for item in items_result.scalars().all():
                item.cluster_id = primary.id

            other.status = "merged"
            other.reviewed_by = UUID(user_id)

        # recalculate time window
        items_result = await session.execute(
            select(EventClusterItem).where(
                EventClusterItem.cluster_id == primary.id,
            )
        )
        all_items = list(items_result.scalars().all())
        if all_items:
            primary.time_window_start = min(
                i.absolute_time_start for i in all_items
            )
            primary.time_window_end = max(
                i.absolute_time_end or i.absolute_time_start for i in all_items
            )

    await session.commit()

    loaded = await get_cluster(session, str(primary.id), case_id)
    assert loaded is not None
    return loaded


async def split_cluster(
    session: AsyncSession,
    cluster_id: str,
    case_id: str,
    item_ids: list[str],
    user_id: str,
) -> EventCluster:
    """split items from a cluster into a new cluster."""
    original = await _load_cluster(session, cluster_id, case_id)

    # load items to move
    items_to_move = []
    for iid in item_ids:
        item_result = await session.execute(
            select(EventClusterItem).where(
                EventClusterItem.id == UUID(iid),
                EventClusterItem.cluster_id == original.id,
            )
        )
        item = item_result.scalar_one_or_none()
        if item is None:
            from fastapi import HTTPException

            raise HTTPException(
                status_code=404,
                detail=f"item {iid} not found in cluster",
            )
        items_to_move.append(item)

    # calculate time window for new cluster
    starts = [i.absolute_time_start for i in items_to_move]
    ends = [i.absolute_time_end or i.absolute_time_start for i in items_to_move]

    async with session.begin_nested():
        new_cluster = EventCluster(
            case_id=UUID(case_id),
            status="proposed",
            proposed_title=(f"Split from: {original.proposed_title}"),
            proposed_description=None,
            time_window_start=min(starts),
            time_window_end=max(ends),
        )
        session.add(new_cluster)
        await session.flush()

        for item in items_to_move:
            item.cluster_id = new_cluster.id

        # recalculate original's time window
        remaining_result = await session.execute(
            select(EventClusterItem).where(
                EventClusterItem.cluster_id == original.id,
            )
        )
        remaining = list(remaining_result.scalars().all())
        if remaining:
            original.time_window_start = min(
                i.absolute_time_start for i in remaining
            )
            original.time_window_end = max(
                i.absolute_time_end or i.absolute_time_start for i in remaining
            )

    await session.commit()

    loaded = await get_cluster(session, str(new_cluster.id), case_id)
    assert loaded is not None
    return loaded


async def list_clusters(
    session: AsyncSession,
    case_id: str,
    status: str | None = None,
    skip: int = 0,
    limit: int = 50,
) -> tuple[list[EventCluster], int]:
    """list clusters for a case with optional status filter."""
    query = select(EventCluster).where(
        EventCluster.case_id == UUID(case_id),
    )
    if status is not None:
        query = query.where(EventCluster.status == status)

    # total count
    count_query = select(func.count()).select_from(
        query.with_only_columns(EventCluster.id).subquery()
    )
    total_result = await session.execute(count_query)
    total = total_result.scalar_one()

    # paginated results
    query = query.order_by(EventCluster.time_window_start.asc())
    query = query.offset(skip).limit(limit)
    result = await session.execute(query)
    clusters = list(result.scalars().all())

    # load items for each cluster
    for cluster in clusters:
        items_result = await session.execute(
            select(EventClusterItem).where(
                EventClusterItem.cluster_id == cluster.id,
            )
        )
        cluster.items = list(  # type: ignore[attr-defined]
            items_result.scalars().all()
        )

    return clusters, total


async def get_cluster(
    session: AsyncSession,
    cluster_id: str,
    case_id: str,
) -> EventCluster | None:
    """get a single cluster with its items."""
    result = await session.execute(
        select(EventCluster).where(
            EventCluster.id == UUID(cluster_id),
            EventCluster.case_id == UUID(case_id),
        )
    )
    cluster = result.scalar_one_or_none()
    if cluster is None:
        return None

    items_result = await session.execute(
        select(EventClusterItem).where(
            EventClusterItem.cluster_id == cluster.id,
        )
    )
    cluster.items = list(  # type: ignore[attr-defined]
        items_result.scalars().all()
    )
    return cluster


async def _load_cluster(
    session: AsyncSession,
    cluster_id: str,
    case_id: str,
) -> EventCluster:
    """load cluster, verifying case ownership."""
    from fastapi import HTTPException

    result = await session.execute(
        select(EventCluster).where(
            EventCluster.id == UUID(cluster_id),
            EventCluster.case_id == UUID(case_id),
        )
    )
    cluster = result.scalar_one_or_none()
    if cluster is None:
        raise HTTPException(
            status_code=404,
            detail="cluster not found",
        )
    return cluster
