"""temporal activities for the scene detection pipeline.

uses shared engine/session and delegates to scene_detection
service.
"""

import logging
import tempfile
from pathlib import Path
from typing import Any
from uuid import UUID

from sqlalchemy import select
from temporalio import activity

from loom.models.asset import Asset
from loom.services.scene_detection import (
    detect_scenes,
    generate_scene_thumbnails,
    store_scenes,
)
from loom.services.storage import (
    DERIVATIVES_BUCKET,
    ORIGINALS_BUCKET,
    StorageService,
)
from loom.workflows.shared import get_db_session, get_minio_client

logger = logging.getLogger(__name__)


@activity.defn
async def detect_asset_scenes(
    asset_id: str,
) -> list[dict[str, Any]]:
    """download video and run scene detection.

    returns list of scene boundary dicts. idempotent:
    re-running produces the same boundaries.
    """
    logger.info("detecting scenes for asset %s", asset_id)

    async with get_db_session() as session:
        result = await session.execute(
            select(Asset).where(Asset.id == UUID(asset_id))
        )
        asset = result.scalar_one_or_none()
        if asset is None:
            msg = f"asset {asset_id} not found"
            raise ValueError(msg)

        if asset.media_type != "video":
            logger.info(
                "asset %s is not video (%s); skipping scene detection",
                asset_id,
                asset.media_type,
            )
            return []

        storage = StorageService(get_minio_client())

        with tempfile.TemporaryDirectory(prefix="loom_scene_") as tmp_dir:
            suffix = Path(asset.original_filename).suffix
            dest = str(Path(tmp_dir) / f"video{suffix}")
            storage.download_file(
                ORIGINALS_BUCKET,
                asset.storage_key,
                dest,
            )

            scenes = detect_scenes(dest)

    logger.info(
        "detected %d scenes for asset %s",
        len(scenes),
        asset_id,
    )
    return scenes


@activity.defn
async def generate_scene_thumbs(
    asset_id: str,
) -> list[str]:
    """generate thumbnail images for detected scenes.

    downloads video, re-detects scenes, generates
    thumbnails, and uploads to minio. returns list of
    storage keys. idempotent: overwrites existing
    thumbnails.
    """
    logger.info(
        "generating scene thumbnails for asset %s",
        asset_id,
    )

    async with get_db_session() as session:
        result = await session.execute(
            select(Asset).where(Asset.id == UUID(asset_id))
        )
        asset = result.scalar_one_or_none()
        if asset is None:
            msg = f"asset {asset_id} not found"
            raise ValueError(msg)

        if asset.media_type != "video":
            return []

        storage = StorageService(get_minio_client())
        keys: list[str] = []

        with tempfile.TemporaryDirectory(prefix="loom_scene_thumb_") as tmp_dir:
            suffix = Path(asset.original_filename).suffix
            dest = str(Path(tmp_dir) / f"video{suffix}")
            storage.download_file(
                ORIGINALS_BUCKET,
                asset.storage_key,
                dest,
            )

            scenes = detect_scenes(dest)
            thumb_dir = str(Path(tmp_dir) / "thumbs")
            thumb_paths = generate_scene_thumbnails(dest, scenes, thumb_dir)

            case_id = str(asset.case_id)
            base_key = f"{case_id}/{asset_id}/scenes"

            for i, thumb_path in enumerate(thumb_paths):
                key = f"{base_key}/scene_{i + 1:04d}.jpg"
                storage.upload_file(
                    DERIVATIVES_BUCKET,
                    key,
                    thumb_path,
                    "image/jpeg",
                )
                keys.append(key)

                # attach key to scene data for storage
                if i < len(scenes):
                    scenes[i]["thumbnail_key"] = key

    logger.info(
        "generated %d scene thumbnails for asset %s",
        len(keys),
        asset_id,
    )
    return keys


@activity.defn
async def store_scene_results(
    asset_id: str,
) -> None:
    """detect scenes and persist records to the database.

    idempotent: re-running will re-detect and re-insert.
    """
    logger.info("storing scene results for asset %s", asset_id)

    async with get_db_session() as session:
        result = await session.execute(
            select(Asset).where(Asset.id == UUID(asset_id))
        )
        asset = result.scalar_one_or_none()
        if asset is None:
            msg = f"asset {asset_id} not found"
            raise ValueError(msg)

        if asset.media_type != "video":
            return

        storage = StorageService(get_minio_client())

        with tempfile.TemporaryDirectory(prefix="loom_scene_store_") as tmp_dir:
            suffix = Path(asset.original_filename).suffix
            dest = str(Path(tmp_dir) / f"video{suffix}")
            storage.download_file(
                ORIGINALS_BUCKET,
                asset.storage_key,
                dest,
            )

            scenes = detect_scenes(dest)

        records = await store_scenes(session, asset_id, scenes)
        await session.commit()

    logger.info(
        "stored %d scene records for asset %s",
        len(records),
        asset_id,
    )
