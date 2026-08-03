"""recreate a case from a verified portable bundle.

the bundle is verified (manifest + signature) before this runs; here
we rebuild the case tree with FRESH uuids while preserving every
original's content hash verbatim. actor ids from the source deploy
do not exist here, so the source custody chain is embedded inside a
single ``imported`` custody entry per asset rather than replayed as
rows — the chain travels with the evidence without inventing local
actors. the whole recreation runs in one transaction; originals
already moved into WORM are cleaned up if it raises.
"""

from __future__ import annotations

import json
import logging
import zipfile
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from loom.models.annotation import Annotation
from loom.models.asset import Asset
from loom.models.case import Case
from loom.models.chain_of_custody import ChainOfCustodyEntry
from loom.models.timeline import (
    EVENT_STATUS_VALUES,
    TimelineEvent,
    TimelineEventEvidence,
)
from loom.models.transcript import TranscriptSegment
from loom.services.ingest import generate_storage_key
from loom.services.portable_bundle import SignatureStatus
from loom.services.storage_backends import ORIGINALS_BUCKET, StorageBackend
from loom.services.streaming_upload import upload_tmp_dir

logger = logging.getLogger(__name__)

_COPY_CHUNK = 1024 * 1024


def _parse_dt(value: str | None) -> Any:
    if value is None:
        return None
    from datetime import datetime

    return datetime.fromisoformat(value)


def _extract_and_verify(
    zf: zipfile.ZipFile,
    entry_name: str,
    expected_sha: str,
    dest: Path,
) -> None:
    """stream an evidence original out of the zip to ``dest``,
    verifying its sha256 — the manifest was already checked, this
    guards the copy itself."""
    import hashlib

    digest = hashlib.sha256()
    with zf.open(entry_name, "r") as src, dest.open("wb") as out:
        while chunk := src.read(_COPY_CHUNK):
            out.write(chunk)
            digest.update(chunk)
    if digest.hexdigest() != expected_sha:
        raise ValueError(
            f"evidence {entry_name} failed hash check during import"
        )


async def recreate_case_contents(
    session: AsyncSession,
    case: Case,
    bundle_path: Path,
    storage: StorageBackend,
    *,
    importer_id: str,
    signature: SignatureStatus,
    bundle_sha256: str,
    source_deploy: str,
) -> dict[str, int]:
    """populate ``case`` from the bundle; return per-kind counts."""
    importer = UUID(importer_id)
    moved_keys: list[str] = []
    try:
        with zipfile.ZipFile(bundle_path, "r") as zf:
            assets_doc = json.loads(zf.read("data/assets.json"))
            timeline_doc = json.loads(zf.read("data/timeline.json"))
            annotations_doc = json.loads(zf.read("data/annotations.json"))
            transcripts_doc = json.loads(zf.read("data/transcripts.json"))
            custody_doc = json.loads(zf.read("data/custody.json"))

            custody_by_asset = _group_custody(custody_doc)
            asset_map = await _recreate_assets(
                session,
                zf,
                case,
                assets_doc,
                custody_by_asset,
                storage,
                moved_keys,
                importer=importer,
                signature=signature,
                bundle_sha256=bundle_sha256,
                source_deploy=source_deploy,
            )

        event_map = await _recreate_events(
            session, case, timeline_doc["events"], importer
        )
        ann_map = await _recreate_annotations(
            session, case, annotations_doc, asset_map, importer
        )
        await _recreate_links(
            session,
            timeline_doc.get("evidence_links", []),
            event_map,
            asset_map,
            ann_map,
            importer,
        )
        await _recreate_transcripts(session, transcripts_doc, asset_map)
        await session.flush()
    except BaseException:
        # the db transaction rolls back, but originals already moved
        # into WORM would orphan — best-effort remove them
        for key in moved_keys:
            try:
                storage.delete_object(ORIGINALS_BUCKET, key)
            except Exception:
                logger.warning("could not clean orphaned original %s", key)
        raise

    return {
        "assets": len(asset_map),
        "events": len(event_map),
        "annotations": len(ann_map),
    }


def _group_custody(
    custody_doc: list[dict[str, Any]],
) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for entry in custody_doc:
        grouped.setdefault(entry["asset_source_id"], []).append(entry)
    return grouped


async def _recreate_assets(
    session: AsyncSession,
    zf: zipfile.ZipFile,
    case: Case,
    assets_doc: list[dict[str, Any]],
    custody_by_asset: dict[str, list[dict[str, Any]]],
    storage: StorageBackend,
    moved_keys: list[str],
    *,
    importer: UUID,
    signature: SignatureStatus,
    bundle_sha256: str,
    source_deploy: str,
) -> dict[str, UUID]:
    asset_map: dict[str, UUID] = {}
    tmp_dir = upload_tmp_dir()
    for row in assets_doc:
        source_id = row["source_id"]
        new_id = uuid4()
        filename = row["original_filename"]
        key = generate_storage_key(str(case.id), str(new_id), filename)

        # stream the original out of the zip and into WORM storage
        tmp = tmp_dir / f"import-{new_id}"
        entry = f"evidence/{source_id}/{filename}"
        _extract_and_verify(zf, entry, row["sha256_hash"], tmp)
        storage.upload_file_move(
            ORIGINALS_BUCKET, key, str(tmp), row["mime_type"]
        )
        moved_keys.append(key)

        asset = Asset(
            id=new_id,
            case_id=case.id,
            original_filename=filename,
            storage_key=key,
            media_type=row["media_type"],
            mime_type=row["mime_type"],
            file_size_bytes=row["file_size_bytes"],
            sha256_hash=row["sha256_hash"],
            sha512_hash=row["sha512_hash"],
            upload_status="complete",
            uploaded_by=importer,
            processing_status=row.get("processing_status", "pending"),
            capture_time=_parse_dt(row.get("capture_time")),
            metadata_raw=row.get("metadata_raw"),
            metadata_extracted=row.get("metadata_extracted"),
            clock_offset_seconds=row.get("clock_offset_seconds"),
        )
        session.add(asset)
        await session.flush()
        asset_map[source_id] = new_id

        # one imported entry, first in the chain, carrying the source
        # deploy's full custody trail + the bundle provenance
        session.add(
            ChainOfCustodyEntry(
                asset_id=new_id,
                action="imported",
                actor_id=importer,
                detail={
                    "action": "imported_from_bundle",
                    "bundle_sha256": bundle_sha256,
                    "source_deploy": source_deploy,
                    "source_asset_id": source_id,
                    "signature_status": signature.state,
                    "source_custody_chain": custody_by_asset.get(source_id, []),
                },
            )
        )
    await session.flush()
    return asset_map


async def _recreate_events(
    session: AsyncSession,
    case: Case,
    events_doc: list[dict[str, Any]],
    importer: UUID,
) -> dict[str, UUID]:
    event_map: dict[str, UUID] = {}
    for row in events_doc:
        new_id = uuid4()
        event = TimelineEvent(
            id=new_id,
            case_id=case.id,
            title=row["title"],
            description=row.get("description"),
            event_time_start=_parse_dt(row["event_time_start"]),
            event_time_end=_parse_dt(row.get("event_time_end")),
            time_precision=row.get("time_precision", "approximate"),
            # foreign bundles carry whatever status their writer
            # produced; anything outside the model vocabulary would
            # violate the check constraint and abort the import
            status=(
                row["status"]
                if row.get("status") in EVENT_STATUS_VALUES
                else "draft"
            ),
            location_description=row.get("location_description"),
            location_lat=row.get("location_lat"),
            location_lon=row.get("location_lon"),
            location_confidence=row.get("location_confidence", "unknown"),
            created_by=importer,
        )
        session.add(event)
        event_map[row["source_id"]] = new_id
    await session.flush()
    return event_map


async def _recreate_annotations(
    session: AsyncSession,
    case: Case,
    annotations_doc: list[dict[str, Any]],
    asset_map: dict[str, UUID],
    importer: UUID,
) -> dict[str, UUID]:
    ann_map: dict[str, UUID] = {}
    for row in annotations_doc:
        new_id = uuid4()
        asset_src = row.get("asset_source_id")
        ann = Annotation(
            id=new_id,
            case_id=case.id,
            asset_id=asset_map.get(asset_src) if asset_src else None,
            type=row["type"],
            content=row["content"],
            time_start=row.get("time_start"),
            time_end=row.get("time_end"),
            frame_number=row.get("frame_number"),
            spatial_region=row.get("spatial_region"),
            created_by=importer,
        )
        session.add(ann)
        ann_map[row["source_id"]] = new_id
    await session.flush()
    return ann_map


async def _recreate_links(
    session: AsyncSession,
    links_doc: list[dict[str, Any]],
    event_map: dict[str, UUID],
    asset_map: dict[str, UUID],
    ann_map: dict[str, UUID],
    importer: UUID,
) -> None:
    for row in links_doc:
        event_id = event_map.get(row["event_source_id"])
        if event_id is None:
            continue
        asset_src = row.get("asset_source_id")
        ann_src = row.get("annotation_source_id")
        session.add(
            TimelineEventEvidence(
                event_id=event_id,
                asset_id=asset_map.get(asset_src) if asset_src else None,
                annotation_id=ann_map.get(ann_src) if ann_src else None,
                clip_start=row.get("clip_start"),
                clip_end=row.get("clip_end"),
                relationship=row.get("relationship", "supports"),
                linked_by=importer,
            )
        )
    await session.flush()


async def _recreate_transcripts(
    session: AsyncSession,
    transcripts_doc: list[dict[str, Any]],
    asset_map: dict[str, UUID],
) -> None:
    for row in transcripts_doc:
        asset_id = asset_map.get(row["asset_source_id"])
        if asset_id is None:
            continue
        session.add(
            TranscriptSegment(
                asset_id=asset_id,
                start_time=row["start_time"],
                end_time=row["end_time"],
                text=row["text"],
                speaker_label=row.get("speaker_label"),
                language=row.get("language"),
                confidence=row.get("confidence"),
                model_name=row.get("model_name"),
                model_version=row.get("model_version"),
            )
        )
    await session.flush()
