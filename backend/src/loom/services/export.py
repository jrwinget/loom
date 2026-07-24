import hashlib
import json
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from loom.models.annotation import Annotation
from loom.models.asset import Asset
from loom.models.chain_of_custody import ChainOfCustodyEntry
from loom.models.export_bundle import ExportBundle
from loom.models.timeline import TimelineEvent
from loom.services.portable_bundle import (
    BundleVerificationError,
    stream_evidence_entry,
)
from loom.services.storage_backends import ORIGINALS_BUCKET, StorageBackend


async def create_export_record(
    session: AsyncSession,
    case_id: str,
    name: str,
    fmt: str,
    user_id: str,
    options: dict[str, Any] | None = None,
) -> ExportBundle:
    """create a pending export bundle record.

    options is the export request as submitted; it is stored
    verbatim so the builders honor it and the record of what was
    asked for survives completion (manifest is an output slot).
    """
    export = ExportBundle(
        case_id=UUID(case_id),
        name=name,
        format=fmt,
        status="pending",
        storage_key="",
        sha256_hash="",
        options=options,
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
    date_range_end, include_originals, and include_analysis. when
    include_analysis is false the analysis layer (timeline events
    and annotations — attorney work product) is not gathered at
    all, and the manifest's contents section records the exclusion
    explicitly.
    """
    cid = UUID(case_id)
    include_analysis = options.get("include_analysis", True)
    include_originals = options.get("include_originals", False)

    # assets
    asset_query = select(Asset).where(Asset.case_id == cid)
    asset_ids = options.get("asset_ids")
    if asset_ids:
        asset_query = asset_query.where(
            Asset.id.in_([UUID(a) for a in asset_ids])
        )
    asset_result = await session.execute(asset_query)
    assets = list(asset_result.scalars().all())

    events: list[TimelineEvent] = []
    annotations: list[Annotation] = []
    if include_analysis:
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
            event_query = event_query.where(
                TimelineEvent.event_time_start >= dt
            )
        if date_end:
            dt = (
                date_end
                if isinstance(date_end, datetime)
                else datetime.fromisoformat(date_end)
            )
            event_query = event_query.where(
                TimelineEvent.event_time_start <= dt
            )
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

    included: dict[str, int] = {
        "assets": len(assets),
        "chain_of_custody": len(custody_entries),
    }
    excluded: dict[str, str] = {}
    if include_analysis:
        included["timeline_events"] = len(events)
        included["annotations"] = len(annotations)
    else:
        excluded["timeline_events"] = (
            "analysis layer excluded (attorney work product)"
        )
        excluded["annotations"] = (
            "analysis layer excluded (attorney work product)"
        )
    if include_originals:
        included["original_files"] = len(assets)
    else:
        excluded["original_files"] = "not requested"

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
        "include_originals": include_originals,
        "include_analysis": include_analysis,
        "contents": {"included": included, "excluded": excluded},
    }


def _bundle_readme(manifest: dict[str, Any]) -> str:
    """README.txt body with the explicit included/excluded summary."""
    contents = manifest.get("contents", {})
    lines = [
        "Loom Export Bundle",
        "==================",
        "",
        f"Case ID: {manifest['case_id']}",
        "",
        "Included:",
    ]
    for name, count in sorted(contents.get("included", {}).items()):
        lines.append(f"  - {name}: {count}")
    excluded = contents.get("excluded", {})
    if excluded:
        lines.append("")
        lines.append("Excluded:")
        for name, reason in sorted(excluded.items()):
            lines.append(f"  - {name}: {reason}")
    lines.append("")
    return "\n".join(lines)


def package_export_bundle(
    manifest: dict[str, Any],
    storage_service: StorageBackend,
    dest_path: Path,
) -> tuple[str, list[dict[str, str]]]:
    """write the zip bundle to dest_path; return (sha256, exported).

    the caller moves dest_path into storage (upload_file_move) so
    multi-gigabyte bundles never live in memory. when the manifest
    asks for originals, each is streamed out of the originals
    bucket and re-hashed on the way into the zip; a digest that no
    longer matches the ingest hash aborts the export rather than
    shipping silently corrupted evidence. exported lists the assets
    whose originals were included and verified, for the custody
    trail.
    """
    include_analysis = manifest.get("include_analysis", True)
    exported: list[dict[str, str]] = []

    with zipfile.ZipFile(dest_path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("manifest.json", json.dumps(manifest, indent=2))
        zf.writestr("README.txt", _bundle_readme(manifest))

        # the analysis layer is written only when requested; an
        # excluded layer is absent entirely (the readme and manifest
        # contents section say why) rather than shipped as empty
        # files that imply nothing exists
        if include_analysis:
            zf.writestr(
                "timeline.json",
                json.dumps(manifest["timeline_events"], indent=2),
            )
            zf.writestr(
                "annotations.json",
                json.dumps(manifest["annotations"], indent=2),
            )

        zf.writestr(
            "chain_of_custody.json",
            json.dumps(manifest["chain_of_custody"], indent=2),
        )

        # hashes recorded at ingest; originals below are re-verified
        # against these at export time when included
        checksums = "\n".join(
            f"{a['sha256_hash']}  {a['original_filename']}"
            for a in manifest["assets"]
        )
        zf.writestr("checksums.sha256", checksums)

        if manifest.get("include_originals"):
            for asset in manifest["assets"]:
                entry_name = (
                    f"evidence/{asset['id']}/{asset['original_filename']}"
                )
                _size, stream = storage_service.get_object_stream(
                    ORIGINALS_BUCKET, asset["storage_key"]
                )
                digest = stream_evidence_entry(zf, entry_name, stream)
                if digest != asset["sha256_hash"]:
                    raise BundleVerificationError(
                        f"stored bytes for {asset['id']} do not match "
                        "the recorded sha256 — refusing to export a "
                        "corrupt original"
                    )
                exported.append({"id": asset["id"], "sha256": digest})

    sha256 = hashlib.sha256()
    with dest_path.open("rb") as fh:
        while chunk := fh.read(1024 * 1024):
            sha256.update(chunk)
    return sha256.hexdigest(), exported
