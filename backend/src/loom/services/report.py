import logging
import warnings
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import UUID

from jinja2 import Environment, FileSystemLoader
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from loom.models.annotation import Annotation
from loom.models.asset import Asset
from loom.models.case import Case
from loom.models.chain_of_custody import ChainOfCustodyEntry
from loom.models.timeline import (
    TimelineEvent,
    TimelineEventEvidence,
)

logger = logging.getLogger(__name__)

_TEMPLATE_DIR = Path(__file__).resolve().parent.parent / "templates"


def _coerce_datetime(value: Any) -> datetime | None:
    """coerce a value to datetime if it's a string."""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    return datetime.fromisoformat(value)


def _format_dt(value: Any) -> str | None:
    """format a datetime or string for output."""
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, str):
        return value
    return None


async def _fetch_events(
    session: AsyncSession,
    cid: UUID,
    options: dict[str, Any],
) -> list[TimelineEvent]:
    """fetch timeline events with optional filters."""
    query = select(TimelineEvent).where(TimelineEvent.case_id == cid)
    event_ids = options.get("event_ids")
    if event_ids:
        query = query.where(TimelineEvent.id.in_([UUID(e) for e in event_ids]))
    date_start = _coerce_datetime(options.get("date_range_start"))
    if date_start:
        query = query.where(TimelineEvent.event_time_start >= date_start)
    date_end = _coerce_datetime(options.get("date_range_end"))
    if date_end:
        query = query.where(TimelineEvent.event_time_start <= date_end)
    query = query.order_by(TimelineEvent.event_time_start.asc())
    result = await session.execute(query)
    return list(result.scalars().all())


async def _build_event_evidence(
    session: AsyncSession,
    event: TimelineEvent,
    asset_map: dict[UUID, Asset],
    include_contradictions: bool,
) -> dict[str, Any]:
    """build evidence lists for a single event."""
    ev_info: dict[str, Any] = {
        "id": str(event.id),
        "title": event.title,
        "description": event.description,
        "event_time_start": event.event_time_start,
        "event_time_end": event.event_time_end,
        "status": event.status,
        "location_description": event.location_description,
        "supporting": [],
        "contradicting": [],
        "context": [],
    }

    ev_result = await session.execute(
        select(TimelineEventEvidence).where(
            TimelineEventEvidence.event_id == event.id
        )
    )
    for link in ev_result.scalars().all():
        asset = asset_map.get(link.asset_id) if link.asset_id else None
        link_info = {
            "original_filename": (
                asset.original_filename if asset else "unknown"
            ),
            "clip_start": link.clip_start,
            "clip_end": link.clip_end,
            "notes": link.notes,
            "relationship": link.relationship,
        }
        if link.relationship == "supports":
            ev_info["supporting"].append(link_info)
        elif link.relationship == "contradicts" and include_contradictions:
            ev_info["contradicting"].append(link_info)
        elif link.relationship == "context":
            ev_info["context"].append(link_info)

    return ev_info


async def build_report_data(
    session: AsyncSession,
    case_id: str,
    options: dict[str, Any],
) -> dict[str, Any]:
    """gather case data for report rendering.

    options may include event_ids, date_range_start,
    date_range_end, include_evidence, include_contradictions,
    include_custody, executive_summary.
    """
    cid = UUID(case_id)

    # case info
    case_result = await session.execute(select(Case).where(Case.id == cid))
    case = case_result.scalar_one_or_none()
    case_info = {
        "name": case.name if case else "Unknown Case",
        "description": case.description if case else None,
        "status": case.status if case else "unknown",
    }

    events = await _fetch_events(session, cid, options)

    # build asset lookup for evidence references
    asset_query = select(Asset).where(Asset.case_id == cid)
    asset_result = await session.execute(asset_query)
    assets = list(asset_result.scalars().all())
    asset_map: dict[UUID, Asset] = {a.id: a for a in assets}

    # evidence links per event
    include_evidence = options.get("include_evidence", True)
    include_contradictions = options.get("include_contradictions", True)
    event_data = []
    for event in events:
        if include_evidence:
            ev_info = await _build_event_evidence(
                session,
                event,
                asset_map,
                include_contradictions,
            )
        else:
            ev_info = {
                "id": str(event.id),
                "title": event.title,
                "description": event.description,
                "event_time_start": event.event_time_start,
                "event_time_end": event.event_time_end,
                "status": event.status,
                "location_description": (event.location_description),
                "supporting": [],
                "contradicting": [],
                "context": [],
            }
        event_data.append(ev_info)

    # annotations
    ann_query = select(Annotation).where(Annotation.case_id == cid)
    ann_result = await session.execute(ann_query)
    annotations = [
        {
            "id": str(a.id),
            "type": a.type,
            "content": a.content,
            "asset_id": (str(a.asset_id) if a.asset_id else None),
        }
        for a in ann_result.scalars().all()
    ]

    # chain of custody (optional)
    custody: list[dict[str, Any]] = []
    if options.get("include_custody", False):
        asset_id_list = [a.id for a in assets]
        if asset_id_list:
            coc_q = select(ChainOfCustodyEntry).where(
                ChainOfCustodyEntry.asset_id.in_(asset_id_list)
            )
            coc_result = await session.execute(coc_q)
            custody = [
                {
                    "asset_id": str(c.asset_id),
                    "action": c.action,
                    "actor_id": str(c.actor_id),
                    "timestamp": c.timestamp.isoformat(),
                }
                for c in coc_result.scalars().all()
            ]

    # asset index for the evidence index section
    asset_index = [
        {
            "id": str(a.id),
            "original_filename": a.original_filename,
            "media_type": a.media_type,
            "sha256_hash": a.sha256_hash,
            "file_size_bytes": a.file_size_bytes,
        }
        for a in assets
    ]

    date_start = options.get("date_range_start")
    date_end = options.get("date_range_end")

    return {
        "case": case_info,
        "events": event_data,
        "annotations": annotations,
        "chain_of_custody": custody,
        "assets": asset_index,
        "generated_at": datetime.utcnow().isoformat(),
        "executive_summary": options.get("executive_summary"),
        "date_range_start": _format_dt(date_start),
        "date_range_end": _format_dt(date_end),
    }


def render_report_html(report_data: dict[str, Any]) -> str:
    """render jinja2 template with report data."""
    env = Environment(
        loader=FileSystemLoader(str(_TEMPLATE_DIR)),
        autoescape=True,
    )
    template = env.get_template("report.html")
    result: str = template.render(**report_data)
    return result


def render_report_pdf(html_content: str) -> bytes:
    """convert html to pdf using weasyprint.

    raises ImportError if weasyprint is not installed.
    """
    try:
        from weasyprint import HTML
    except ImportError as err:
        raise ImportError(
            "weasyprint is required for pdf generation. "
            "install with: pip install 'loom[report]'"
        ) from err

    doc = HTML(string=html_content)
    pdf_bytes: bytes = doc.write_pdf()
    return pdf_bytes


async def generate_report(
    session: AsyncSession,
    case_id: str,
    options: dict[str, Any],
) -> tuple[str, bytes]:
    """orchestrate report generation.

    returns (html_content, pdf_bytes). if weasyprint is not
    available, returns (html_content, b"") with a warning.
    """
    data = await build_report_data(session, case_id, options)
    html = render_report_html(data)

    try:
        pdf_bytes = render_report_pdf(html)
    except ImportError:
        warnings.warn(
            "weasyprint not installed, skipping pdf",
            stacklevel=2,
        )
        pdf_bytes = b""

    return html, pdf_bytes
