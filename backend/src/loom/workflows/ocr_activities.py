"""temporal activities for the ocr pipeline.

uses shared engine/session and delegates to ocr service.
"""

import logging
import tempfile
import time
from pathlib import Path
from typing import Any
from uuid import UUID

from sqlalchemy import select
from temporalio import activity

from loom.metrics import ingest_workflow_duration
from loom.models.asset import Asset
from loom.services.ocr import run_ocr_on_asset, store_ocr_regions
from loom.services.storage import ORIGINALS_BUCKET, StorageService
from loom.workflows.shared import get_db_session, get_minio_client

logger = logging.getLogger(__name__)


@activity.defn
async def prepare_ocr_input(
    asset_id: str,
) -> dict[str, Any]:
    """download asset and prepare for ocr.

    returns a dict with asset_path and media_type for the
    next activity. idempotent: re-downloading is safe.
    """
    start = time.monotonic()
    try:
        logger.info(
            "preparing ocr input for asset %s", asset_id
        )

        async with get_db_session() as session:
            result = await session.execute(
                select(Asset).where(
                    Asset.id == UUID(asset_id)
                )
            )
            asset = result.scalar_one_or_none()
            if asset is None:
                msg = f"asset {asset_id} not found"
                raise ValueError(msg)

            storage = StorageService(get_minio_client())

            tmp_dir = tempfile.mkdtemp(prefix="loom_ocr_")
            suffix = Path(asset.original_filename).suffix
            dest = str(Path(tmp_dir) / f"asset{suffix}")
            storage.download_file(
                ORIGINALS_BUCKET,
                asset.storage_key,
                dest,
            )

        return {
            "asset_id": asset_id,
            "asset_path": dest,
            "media_type": asset.media_type,
        }
    finally:
        duration = time.monotonic() - start
        ingest_workflow_duration.labels(
            activity="ocr_prepare"
        ).observe(duration)


@activity.defn
async def run_ocr(
    asset_id: str,
) -> dict[str, Any]:
    """run ocr on the asset file.

    expects prepare_ocr_input to have been called first.
    re-downloads if the temp file is missing (idempotent).
    returns regions list for storage.
    """
    start = time.monotonic()
    try:
        logger.info("running ocr for asset %s", asset_id)

        async with get_db_session() as session:
            result = await session.execute(
                select(Asset).where(
                    Asset.id == UUID(asset_id)
                )
            )
            asset = result.scalar_one_or_none()
            if asset is None:
                msg = f"asset {asset_id} not found"
                raise ValueError(msg)

            storage = StorageService(get_minio_client())

            with tempfile.TemporaryDirectory(
                prefix="loom_ocr_run_"
            ) as tmp_dir:
                suffix = Path(asset.original_filename).suffix
                dest = str(Path(tmp_dir) / f"asset{suffix}")
                storage.download_file(
                    ORIGINALS_BUCKET,
                    asset.storage_key,
                    dest,
                )

                regions = run_ocr_on_asset(
                    dest, asset.media_type
                )

        logger.info(
            "ocr found %d regions for asset %s",
            len(regions),
            asset_id,
        )
        return {
            "asset_id": asset_id,
            "regions": regions,
        }
    finally:
        duration = time.monotonic() - start
        ingest_workflow_duration.labels(
            activity="ocr_process"
        ).observe(duration)


@activity.defn
async def store_ocr_results(
    asset_id: str,
) -> dict[str, Any]:
    """run ocr and store results in the database.

    idempotent: re-running will re-detect and re-insert.
    callers should ensure old regions are cleared if needed.
    """
    start = time.monotonic()
    try:
        logger.info(
            "storing ocr results for asset %s", asset_id
        )

        async with get_db_session() as session:
            result = await session.execute(
                select(Asset).where(
                    Asset.id == UUID(asset_id)
                )
            )
            asset = result.scalar_one_or_none()
            if asset is None:
                msg = f"asset {asset_id} not found"
                raise ValueError(msg)

            storage = StorageService(get_minio_client())

            with tempfile.TemporaryDirectory(
                prefix="loom_ocr_store_"
            ) as tmp_dir:
                suffix = Path(asset.original_filename).suffix
                dest = str(Path(tmp_dir) / f"asset{suffix}")
                storage.download_file(
                    ORIGINALS_BUCKET,
                    asset.storage_key,
                    dest,
                )

                regions = run_ocr_on_asset(
                    dest, asset.media_type
                )

            records = await store_ocr_regions(
                session, asset_id, regions
            )
            await session.commit()

        logger.info(
            "stored %d ocr regions for asset %s",
            len(records),
            asset_id,
        )
        return {
            "asset_id": asset_id,
            "regions_stored": len(records),
        }
    finally:
        duration = time.monotonic() - start
        ingest_workflow_duration.labels(
            activity="ocr_store"
        ).observe(duration)
