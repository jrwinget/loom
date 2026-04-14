import hashlib
import io
import json
import zipfile
from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from loom.models.annotation import Annotation
from loom.models.asset import Asset
from loom.models.chain_of_custody import ChainOfCustodyEntry
from loom.models.export_bundle import ExportBundle
from loom.models.timeline import TimelineEvent
from loom.services.storage import DERIVATIVES_BUCKET, StorageService


async def create_export_record(
    session: AsyncSession,
    case_id: str,
    name: str,
    fmt: str,
    user_id: str,
) -> ExportBundle:
    """create a pending export bundle record."""
    export = ExportBundle(
        case_id=UUID(case_id),
        name=name,
        format=fmt,
        status="pending",
        storage_key="",
        sha256_hash="",
        created_by=UUID(user_id),
    )
    session.add(export)
    await session.commit()
    await session.refresh(export)
    return export


async def list_exports(
    session: AsyncSession,
    case_id: str,
    skip: int = 0,
    limit: int = 20,
) -> tuple[list[ExportBundle], int]:
    """list exports for a case with pagination."""
    count_q = select(func.count(ExportBundle.id)).where(
        ExportBundle.case_id == UUID(case_id)
    )
    total_result = await session.execute(count_q)
    total = total_result.scalar_one()

    query = (
        select(ExportBundle)
        .where(ExportBundle.case_id == UUID(case_id))
        .offset(skip)
        .limit(limit)
        .order_by(ExportBundle.created_at.desc())
    )
    result = await session.execute(query)
    exports = list(result.scalars().all())
    return exports, total


async def get_export(
    session: AsyncSession,
    export_id: str,
) -> ExportBundle | None:
    """get a single export by id."""
    result = await session.execute(
        select(ExportBundle).where(ExportBundle.id == UUID(export_id))
    )
    return result.scalar_one_or_none()


async def build_export_manifest(
    session: AsyncSession,
    case_id: str,
    options: dict[str, Any],
) -> dict[str, Any]:
    """gather all data for export and return as structured dict.

    options may include event_ids, asset_ids, date_range_start,
    date_range_end, and include_originals.
    """
    cid = UUID(case_id)

    # assets
    asset_query = select(Asset).where(Asset.case_id == cid)
    asset_ids = options.get("asset_ids")
    if asset_ids:
        asset_query = asset_query.where(
            Asset.id.in_([UUID(a) for a in asset_ids])
        )
    asset_result = await session.execute(asset_query)
    assets = list(asset_result.scalars().all())

    # timeline events
    event_query = select(TimelineEvent).where(TimelineEvent.case_id == cid)
    event_ids = options.get("event_ids")
    if event_ids:
        event_query = event_query.where(
            TimelineEvent.id.in_([UUID(e) for e in event_ids])
        )
    date_start = options.get("date_range_start")
    date_end = options.get("date_range_end")
    if date_start:
        dt = (
            date_start
            if isinstance(date_start, datetime)
            else datetime.fromisoformat(date_start)
        )
        event_query = event_query.where(TimelineEvent.event_time_start >= dt)
    if date_end:
        dt = (
            date_end
            if isinstance(date_end, datetime)
            else datetime.fromisoformat(date_end)
        )
        event_query = event_query.where(TimelineEvent.event_time_start <= dt)
    event_result = await session.execute(event_query)
    events = list(event_result.scalars().all())

    # annotations
    ann_query = select(Annotation).where(Annotation.case_id == cid)
    ann_result = await session.execute(ann_query)
    annotations = list(ann_result.scalars().all())

    # chain of custody (for assets in this case)
    asset_id_list = [a.id for a in assets]
    custody_entries: list[ChainOfCustodyEntry] = []
    if asset_id_list:
        coc_query = select(ChainOfCustodyEntry).where(
            ChainOfCustodyEntry.asset_id.in_(asset_id_list)
        )
        coc_result = await session.execute(coc_query)
        custody_entries = list(coc_result.scalars().all())

    return {
        "case_id": case_id,
        "assets": [
            {
                "id": str(a.id),
                "original_filename": a.original_filename,
                "media_type": a.media_type,
                "mime_type": a.mime_type,
                "file_size_bytes": a.file_size_bytes,
                "sha256_hash": a.sha256_hash,
                "storage_key": a.storage_key,
            }
            for a in assets
        ],
        "timeline_events": [
            {
                "id": str(e.id),
                "title": e.title,
                "description": e.description,
                "event_time_start": (e.event_time_start.isoformat()),
                "event_time_end": (
                    e.event_time_end.isoformat() if e.event_time_end else None
                ),
                "status": e.status,
            }
            for e in events
        ],
        "annotations": [
            {
                "id": str(ann.id),
                "asset_id": (str(ann.asset_id) if ann.asset_id else None),
                "type": ann.type,
                "content": ann.content,
            }
            for ann in annotations
        ],
        "chain_of_custody": [
            {
                "id": str(c.id),
                "asset_id": str(c.asset_id),
                "action": c.action,
                "actor_id": str(c.actor_id),
                "timestamp": c.timestamp.isoformat(),
            }
            for c in custody_entries
        ],
        "include_originals": options.get("include_originals", False),
    }


def package_export_bundle(
    manifest: dict[str, Any],
    storage_service: StorageService,
    output_key: str,
) -> tuple[str, str]:
    """create a zip bundle from manifest and upload to storage.

    returns (storage_key, sha256_hash).
    """
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        # manifest.json
        manifest_json = json.dumps(manifest, indent=2)
        zf.writestr("manifest.json", manifest_json)

        # readme
        readme = (
            "Loom Export Bundle\n"
            "==================\n\n"
            f"Case ID: {manifest['case_id']}\n"
            f"Assets: {len(manifest['assets'])}\n"
            f"Timeline Events: "
            f"{len(manifest['timeline_events'])}\n"
            f"Annotations: {len(manifest['annotations'])}\n"
            f"Chain of Custody Entries: "
            f"{len(manifest['chain_of_custody'])}\n"
        )
        zf.writestr("README.txt", readme)

        # timeline.json
        timeline_json = json.dumps(manifest["timeline_events"], indent=2)
        zf.writestr("timeline.json", timeline_json)

        # annotations.json
        annotations_json = json.dumps(manifest["annotations"], indent=2)
        zf.writestr("annotations.json", annotations_json)

        # chain_of_custody.json
        coc_json = json.dumps(manifest["chain_of_custody"], indent=2)
        zf.writestr("chain_of_custody.json", coc_json)

        # checksums.sha256
        checksums = "\n".join(
            f"{a['sha256_hash']}  {a['original_filename']}"
            for a in manifest["assets"]
        )
        zf.writestr("checksums.sha256", checksums)

    zip_bytes = buf.getvalue()
    sha256 = hashlib.sha256(zip_bytes).hexdigest()

    # upload to derivatives bucket
    storage_service.upload_bytes(
        DERIVATIVES_BUCKET,
        output_key,
        zip_bytes,
        "application/zip",
    )

    return output_key, sha256
