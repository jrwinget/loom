from typing import Any
from uuid import UUID

from sqlalchemy import String, cast, func, literal, select, union_all
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import Executable

from loom.models.annotation import Annotation
from loom.models.asset import Asset
from loom.models.ocr import OcrRegion
from loom.models.timeline import TimelineEvent
from loom.models.transcript import TranscriptSegment

# valid result type names
VALID_TYPES = {"transcripts", "ocr", "annotations", "events", "assets"}


def _ilike_pattern(query: str) -> str:
    """build an ilike pattern from user query."""
    escaped = (
        query.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    )
    return f"%{escaped}%"


def _build_type_queries(
    case_uuid: UUID,
    pattern: str,
    allowed: set[str],
) -> tuple[list[Any], dict[str, Executable]]:
    """build per-type subqueries and facet count queries."""
    subqueries: list[Any] = []
    facet_queries: dict[str, Executable] = {}

    asset_case_filter = select(Asset.id).where(Asset.case_id == case_uuid)

    if "transcripts" in allowed:
        sq = select(
            literal("transcript").label("type"),
            cast(TranscriptSegment.id, String).label("id"),
            TranscriptSegment.text.label("text"),
            cast(TranscriptSegment.asset_id, String).label("asset_id"),
            literal(0.0).label("relevance_score"),
            TranscriptSegment.speaker_label.label("speaker"),
            TranscriptSegment.start_time.label("start_time"),
        ).where(
            TranscriptSegment.asset_id.in_(asset_case_filter),
            TranscriptSegment.text.ilike(pattern),
        )
        subqueries.append(
            sq.with_only_columns(
                sq.c.type,
                sq.c.id,
                sq.c.text,
                sq.c.asset_id,
                sq.c.relevance_score,
            )
        )
        facet_queries["transcripts"] = select(func.count()).select_from(
            select(TranscriptSegment.id)
            .where(
                TranscriptSegment.asset_id.in_(asset_case_filter),
                TranscriptSegment.text.ilike(pattern),
            )
            .subquery()
        )

    if "ocr" in allowed:
        sq_ocr = select(
            literal("ocr").label("type"),
            cast(OcrRegion.id, String).label("id"),
            OcrRegion.text.label("text"),
            cast(OcrRegion.asset_id, String).label("asset_id"),
            literal(0.0).label("relevance_score"),
        ).where(
            OcrRegion.asset_id.in_(asset_case_filter),
            OcrRegion.text.ilike(pattern),
        )
        subqueries.append(sq_ocr)
        facet_queries["ocr"] = select(func.count()).select_from(
            select(OcrRegion.id)
            .where(
                OcrRegion.asset_id.in_(asset_case_filter),
                OcrRegion.text.ilike(pattern),
            )
            .subquery()
        )

    if "annotations" in allowed:
        sq_ann = select(
            literal("annotation").label("type"),
            cast(Annotation.id, String).label("id"),
            Annotation.content.label("text"),
            cast(Annotation.asset_id, String).label("asset_id"),
            literal(0.0).label("relevance_score"),
        ).where(
            Annotation.case_id == case_uuid,
            Annotation.content.ilike(pattern),
        )
        subqueries.append(sq_ann)
        facet_queries["annotations"] = select(func.count()).select_from(
            select(Annotation.id)
            .where(
                Annotation.case_id == case_uuid,
                Annotation.content.ilike(pattern),
            )
            .subquery()
        )

    if "events" in allowed:
        evt_match = TimelineEvent.title.ilike(
            pattern
        ) | TimelineEvent.description.ilike(pattern)
        sq_evt = select(
            literal("event").label("type"),
            cast(TimelineEvent.id, String).label("id"),
            TimelineEvent.title.label("text"),
            literal(None).label("asset_id"),
            literal(0.0).label("relevance_score"),
        ).where(TimelineEvent.case_id == case_uuid, evt_match)
        subqueries.append(sq_evt)
        facet_queries["events"] = select(func.count()).select_from(
            select(TimelineEvent.id)
            .where(
                TimelineEvent.case_id == case_uuid,
                evt_match,
            )
            .subquery()
        )

    if "assets" in allowed:
        sq_asset = select(
            literal("asset").label("type"),
            cast(Asset.id, String).label("id"),
            Asset.original_filename.label("text"),
            cast(Asset.id, String).label("asset_id"),
            literal(0.0).label("relevance_score"),
        ).where(
            Asset.case_id == case_uuid,
            Asset.original_filename.ilike(pattern),
        )
        subqueries.append(sq_asset)
        facet_queries["assets"] = select(func.count()).select_from(
            select(Asset.id)
            .where(
                Asset.case_id == case_uuid,
                Asset.original_filename.ilike(pattern),
            )
            .subquery()
        )

    return subqueries, facet_queries


async def search_case(
    session: AsyncSession,
    case_id: str,
    query: str,
    result_types: list[str] | None = None,
    skip: int = 0,
    limit: int = 50,
) -> dict[str, Any]:
    """search across multiple tables in a case.

    uses postgresql full-text search when available,
    falls back to ilike for sqlite compatibility.
    """
    case_uuid = UUID(case_id)
    allowed = set(result_types) & VALID_TYPES if result_types else VALID_TYPES
    pattern = _ilike_pattern(query)

    subqueries, facet_queries = _build_type_queries(case_uuid, pattern, allowed)

    # build facets — single query using union all
    facets: dict[str, int] = {ftype: 0 for ftype in VALID_TYPES}
    if facet_queries:
        facet_subqueries = []
        for ftype, fq in facet_queries.items():
            facet_subqueries.append(
                select(
                    literal(ftype).label("facet_type"),
                    fq.scalar_subquery().label("cnt"),  # type: ignore[attr-defined]
                )
            )
        facet_union = union_all(*facet_subqueries).subquery()
        facet_result = await session.execute(
            select(
                facet_union.c.facet_type,
                facet_union.c.cnt,
            )
        )
        for row in facet_result.all():
            facets[row.facet_type] = row.cnt

    total = sum(facets.values())

    # build unified query
    if not subqueries:
        return {"results": [], "total": 0, "facets": facets}

    unified = union_all(*subqueries).subquery()
    paginated = select(unified).offset(skip).limit(limit)
    result = await session.execute(paginated)
    rows = result.all()

    results = []
    for row in rows:
        results.append(
            {
                "type": row.type,
                "id": row.id,
                "text": row.text,
                "asset_id": row.asset_id,
                "relevance_score": row.relevance_score or 0.0,
                "metadata": {},
            }
        )

    return {"results": results, "total": total, "facets": facets}


async def search_transcripts(
    session: AsyncSession,
    case_id: str,
    query: str,
    skip: int = 0,
    limit: int = 50,
) -> tuple[list[Any], int]:
    """search only transcript segments in a case."""
    case_uuid = UUID(case_id)
    pattern = _ilike_pattern(query)

    # count
    count_q = select(func.count()).select_from(
        select(TranscriptSegment.id)
        .where(
            TranscriptSegment.asset_id.in_(
                select(Asset.id).where(Asset.case_id == case_uuid)
            ),
            TranscriptSegment.text.ilike(pattern),
        )
        .subquery()
    )
    total_result = await session.execute(count_q)
    total = total_result.scalar_one()

    # results
    q = (
        select(TranscriptSegment)
        .where(
            TranscriptSegment.asset_id.in_(
                select(Asset.id).where(Asset.case_id == case_uuid)
            ),
            TranscriptSegment.text.ilike(pattern),
        )
        .offset(skip)
        .limit(limit)
    )
    result = await session.execute(q)
    segments = list(result.scalars().all())

    return segments, total


async def search_annotations(
    session: AsyncSession,
    case_id: str,
    query: str,
    skip: int = 0,
    limit: int = 50,
) -> tuple[list[Any], int]:
    """search only annotations in a case."""
    case_uuid = UUID(case_id)
    pattern = _ilike_pattern(query)

    count_q = select(func.count()).select_from(
        select(Annotation.id)
        .where(
            Annotation.case_id == case_uuid,
            Annotation.content.ilike(pattern),
        )
        .subquery()
    )
    total_result = await session.execute(count_q)
    total = total_result.scalar_one()

    q = (
        select(Annotation)
        .where(
            Annotation.case_id == case_uuid,
            Annotation.content.ilike(pattern),
        )
        .offset(skip)
        .limit(limit)
    )
    result = await session.execute(q)
    annotations = list(result.scalars().all())

    return annotations, total
