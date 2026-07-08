"""Temporal activities for URL-sourced ingestion.

The download-and-provenance activity is monolithic because the
downloaded bytes live in a local tempfile that cannot cross
activity boundaries cleanly. The wayback snapshot is a separate
activity so its non-blocking failure mode stays isolated from the
authoritative provenance record.
"""

import logging
import tempfile
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import UUID

from sqlalchemy import select
from temporalio import activity

from loom.metrics import ingest_workflow_duration
from loom.models.asset import Asset
from loom.models.chain_of_custody import ChainOfCustodyEntry
from loom.services.hashing import compute_hashes_from_file
from loom.services.ingest import (
    detect_media_type,
    generate_storage_key,
)
from loom.services.storage_backends import ORIGINALS_BUCKET
from loom.services.url_ingest import (
    ExtractorUnavailableError,
    select_extractor,
    snapshot_url,
)
from loom.workflows.shared import get_db_session, get_storage_backend

logger = logging.getLogger(__name__)


@activity.defn
async def download_url_and_record_provenance(
    asset_id: str,
    url: str,
) -> dict[str, Any]:
    """Download URL bytes, record provenance, upload to MinIO.

    Idempotent: re-running re-computes hashes and overwrites the
    storage object; custody entries are de-duplicated by action.
    Returns a summary dict for observability.
    """
    start = time.monotonic()
    try:
        logger.info(
            "downloading url %s for asset %s",
            url,
            asset_id,
        )
        extractor = select_extractor(url)

        with tempfile.TemporaryDirectory(
            prefix="loom_url_ingest_",
        ) as tmp_dir:
            tmp_path = Path(tmp_dir)
            try:
                resource = extractor.extract(url, tmp_path)
            except ExtractorUnavailableError:
                # re-raise so the workflow fails loudly: this should
                # never happen once the api endpoint pre-checks
                # availability, but keep the guard.
                raise

            sha256, sha512 = compute_hashes_from_file(
                resource.local_path,
            )
            file_size = resource.local_path.stat().st_size
            retrieved_at = datetime.now(UTC)

            async with get_db_session() as session:
                result = await session.execute(
                    select(Asset).where(
                        Asset.id == UUID(asset_id),
                    )
                )
                asset = result.scalar_one_or_none()
                if asset is None:
                    msg = f"asset {asset_id} not found"
                    raise ValueError(msg)

                storage_key = generate_storage_key(
                    str(asset.case_id),
                    asset_id,
                    resource.filename,
                )

                storage = get_storage_backend()
                storage.upload_file(
                    ORIGINALS_BUCKET,
                    storage_key,
                    str(resource.local_path),
                    resource.content_type,
                )

                media_type = (
                    detect_media_type(resource.content_type) or "document"
                )

                asset.storage_key = storage_key
                asset.original_filename = resource.filename
                asset.mime_type = resource.content_type
                asset.media_type = media_type
                asset.file_size_bytes = file_size
                asset.sha256_hash = sha256
                asset.sha512_hash = sha512
                asset.upload_status = "complete"
                asset.source_uri = url
                asset.source_canonical_uri = resource.canonical_url
                asset.source_method = resource.source_method
                asset.source_downloader = resource.downloader
                asset.source_downloader_version = resource.downloader_version
                asset.source_retrieved_at = retrieved_at
                asset.source_response_headers = (
                    dict(resource.response_headers)
                    if resource.response_headers is not None
                    else None
                )
                asset.source_extractor_info = (
                    dict(resource.extractor_info)
                    if resource.extractor_info is not None
                    else None
                )

                existing = await session.execute(
                    select(ChainOfCustodyEntry).where(
                        ChainOfCustodyEntry.asset_id == UUID(asset_id),
                        ChainOfCustodyEntry.action == "url_ingest",
                    )
                )
                if existing.scalar_one_or_none() is None:
                    entry = ChainOfCustodyEntry(
                        asset_id=UUID(asset_id),
                        action="url_ingest",
                        actor_id=asset.uploaded_by,
                        detail={
                            "url": url,
                            "canonical_url": resource.canonical_url,
                            "downloader": resource.downloader,
                            "downloader_version": (resource.downloader_version),
                            "retrieved_at": (retrieved_at.isoformat()),
                            "sha256": sha256,
                            "source_method": resource.source_method,
                        },
                    )
                    session.add(entry)

                await session.commit()

        logger.info(
            "url ingest complete for asset %s (sha256=%s, size=%d)",
            asset_id,
            sha256,
            file_size,
        )
        return {
            "asset_id": asset_id,
            "sha256": sha256,
            "file_size_bytes": file_size,
            "downloader": resource.downloader,
            "downloader_version": resource.downloader_version,
            "source_method": resource.source_method,
            "canonical_url": resource.canonical_url,
        }
    finally:
        duration = time.monotonic() - start
        ingest_workflow_duration.labels(
            activity="url_ingest_download",
        ).observe(duration)


@activity.defn
async def attempt_wayback_snapshot(
    asset_id: str,
    url: str,
) -> str | None:
    """Best-effort Wayback Machine snapshot.

    On success, updates asset.source_wayback_url and inserts a
    custody entry. On failure, logs and returns None — the rest
    of the ingest pipeline continues regardless.
    """
    start = time.monotonic()
    try:
        archive_url = snapshot_url(url)
        if archive_url is None:
            logger.info(
                "wayback snapshot unavailable for asset %s",
                asset_id,
            )
            return None

        async with get_db_session() as session:
            result = await session.execute(
                select(Asset).where(
                    Asset.id == UUID(asset_id),
                )
            )
            asset = result.scalar_one_or_none()
            if asset is None:
                # asset may have been deleted; snapshot is informational
                logger.warning(
                    "asset %s not found for wayback snapshot",
                    asset_id,
                )
                return archive_url

            asset.source_wayback_url = archive_url

            existing = await session.execute(
                select(ChainOfCustodyEntry).where(
                    ChainOfCustodyEntry.asset_id == UUID(asset_id),
                    ChainOfCustodyEntry.action == "wayback_snapshot",
                )
            )
            if existing.scalar_one_or_none() is None:
                entry = ChainOfCustodyEntry(
                    asset_id=UUID(asset_id),
                    action="wayback_snapshot",
                    actor_id=asset.uploaded_by,
                    detail={
                        "url": url,
                        "archive_url": archive_url,
                    },
                )
                session.add(entry)

            await session.commit()

        logger.info(
            "wayback snapshot recorded for asset %s: %s",
            asset_id,
            archive_url,
        )
        return archive_url
    finally:
        duration = time.monotonic() - start
        ingest_workflow_duration.labels(
            activity="url_ingest_wayback",
        ).observe(duration)
