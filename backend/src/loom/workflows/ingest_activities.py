"""temporal activities for the ingest pipeline.

each activity is a thin wrapper around service-layer logic,
using the shared engine/session for db access and minio for
object storage.
"""

import logging
import tempfile
from pathlib import Path
from typing import Any
from uuid import UUID

from sqlalchemy import select
from temporalio import activity

from loom.models.asset import Asset
from loom.models.chain_of_custody import ChainOfCustodyEntry
from loom.models.derivative import Derivative
from loom.services.hashing import (
    compute_hashes_from_file,
)
from loom.services.metadata import extract_metadata_from_file
from loom.services.storage import (
    DERIVATIVES_BUCKET,
    ORIGINALS_BUCKET,
    StorageService,
)
from loom.workflows.shared import get_db_session, get_minio_client

logger = logging.getLogger(__name__)


@activity.defn
async def verify_asset_hash(asset_id: str) -> bool:
    """download asset from minio, re-hash, compare to db.

    idempotent: re-running will simply re-verify the hash.
    returns True if hashes match, raises on mismatch.
    """
    logger.info("verifying hash for asset %s", asset_id)

    async with get_db_session() as session:
        result = await session.execute(
            select(Asset).where(Asset.id == UUID(asset_id))
        )
        asset = result.scalar_one_or_none()
        if asset is None:
            msg = f"asset {asset_id} not found"
            raise ValueError(msg)

        storage = StorageService(get_minio_client())

        with tempfile.TemporaryDirectory(prefix="loom_hash_") as tmp_dir:
            dest = str(Path(tmp_dir) / "original")
            storage.download_file(
                ORIGINALS_BUCKET,
                asset.storage_key,
                dest,
            )

            sha256, sha512 = compute_hashes_from_file(Path(dest))

        if sha256 != asset.sha256_hash:
            msg = (
                f"sha256 mismatch for asset {asset_id}: "
                f"expected {asset.sha256_hash}, "
                f"got {sha256}"
            )
            raise ValueError(msg)

        if sha512 != asset.sha512_hash:
            msg = (
                f"sha512 mismatch for asset {asset_id}: "
                f"expected {asset.sha512_hash}, "
                f"got {sha512}"
            )
            raise ValueError(msg)

    logger.info("hash verified for asset %s", asset_id)
    return True


@activity.defn
async def extract_asset_metadata(
    asset_id: str,
) -> dict[str, Any]:
    """download file, extract metadata, store in db.

    idempotent: overwrites metadata_raw and
    metadata_extracted on each run.
    """
    logger.info("extracting metadata for asset %s", asset_id)

    async with get_db_session() as session:
        result = await session.execute(
            select(Asset).where(Asset.id == UUID(asset_id))
        )
        asset = result.scalar_one_or_none()
        if asset is None:
            msg = f"asset {asset_id} not found"
            raise ValueError(msg)

        storage = StorageService(get_minio_client())

        with tempfile.TemporaryDirectory(prefix="loom_meta_") as tmp_dir:
            # preserve extension for mime detection
            suffix = Path(asset.original_filename).suffix
            dest = str(Path(tmp_dir) / f"file{suffix}")
            storage.download_file(
                ORIGINALS_BUCKET,
                asset.storage_key,
                dest,
            )

            metadata = extract_metadata_from_file(dest)

        asset.metadata_raw = metadata.get("raw", {})
        asset.metadata_extracted = metadata.get("normalized", {})
        await session.commit()

    logger.info("metadata extracted for asset %s", asset_id)
    return metadata


@activity.defn
async def generate_asset_proxies(
    asset_id: str,
) -> list[str]:
    """generate derivative proxies based on media type.

    idempotent: existing derivatives are not duplicated
    because storage keys are deterministic.
    """
    logger.info("generating proxies for asset %s", asset_id)

    async with get_db_session() as session:
        result = await session.execute(
            select(Asset).where(Asset.id == UUID(asset_id))
        )
        asset = result.scalar_one_or_none()
        if asset is None:
            msg = f"asset {asset_id} not found"
            raise ValueError(msg)

        storage = StorageService(get_minio_client())
        derivative_keys: list[str] = []

        with tempfile.TemporaryDirectory(prefix="loom_proxy_") as tmp_dir:
            suffix = Path(asset.original_filename).suffix
            src = str(Path(tmp_dir) / f"original{suffix}")
            storage.download_file(
                ORIGINALS_BUCKET,
                asset.storage_key,
                src,
            )

            case_id = str(asset.case_id)
            base_key = f"{case_id}/{asset_id}"

            if asset.media_type == "video":
                derivative_keys.extend(
                    _generate_video_derivatives(
                        session,
                        storage,
                        asset_id,
                        src,
                        tmp_dir,
                        base_key,
                    )
                )
            elif asset.media_type == "image":
                derivative_keys.extend(
                    _generate_image_derivatives(
                        session,
                        storage,
                        asset_id,
                        src,
                        tmp_dir,
                        base_key,
                    )
                )
            elif asset.media_type == "audio":
                derivative_keys.extend(
                    _generate_audio_derivatives(
                        session,
                        storage,
                        asset_id,
                        src,
                        tmp_dir,
                        base_key,
                    )
                )

        await session.commit()

    logger.info(
        "generated %d proxies for asset %s",
        len(derivative_keys),
        asset_id,
    )
    return derivative_keys


def _generate_video_derivatives(
    session: Any,
    storage: StorageService,
    asset_id: str,
    src: str,
    tmp_dir: str,
    base_key: str,
) -> list[str]:
    """generate proxy video and thumbnail for a video asset."""
    from loom.services.proxy import (
        generate_thumbnail,
        generate_video_proxy,
    )

    keys: list[str] = []

    # 720p proxy
    try:
        proxy_path = str(Path(tmp_dir) / "proxy.mp4")
        generate_video_proxy(src, proxy_path)
        proxy_key = f"{base_key}/proxy.mp4"
        storage.upload_file(
            DERIVATIVES_BUCKET,
            proxy_key,
            proxy_path,
            "video/mp4",
        )
        _record_derivative(
            session,
            asset_id,
            "proxy",
            proxy_key,
            "video/mp4",
            proxy_path,
        )
        keys.append(proxy_key)
    except RuntimeError:
        logger.warning(
            "ffmpeg unavailable; skipping video proxy for asset %s",
            asset_id,
        )

    # thumbnail
    try:
        thumb_path = str(Path(tmp_dir) / "thumb.jpg")
        generate_thumbnail(src, thumb_path)
        thumb_key = f"{base_key}/thumbnail.jpg"
        storage.upload_file(
            DERIVATIVES_BUCKET,
            thumb_key,
            thumb_path,
            "image/jpeg",
        )
        _record_derivative(
            session,
            asset_id,
            "thumbnail",
            thumb_key,
            "image/jpeg",
            thumb_path,
        )
        keys.append(thumb_key)
    except RuntimeError:
        logger.warning(
            "ffmpeg unavailable; skipping thumbnail for asset %s",
            asset_id,
        )

    return keys


def _generate_image_derivatives(
    session: Any,
    storage: StorageService,
    asset_id: str,
    src: str,
    tmp_dir: str,
    base_key: str,
) -> list[str]:
    """generate thumbnail for an image asset."""
    from loom.services.proxy import generate_image_thumbnail

    keys: list[str] = []
    try:
        thumb_path = str(Path(tmp_dir) / "thumb.jpg")
        generate_image_thumbnail(src, thumb_path)
        thumb_key = f"{base_key}/thumbnail.jpg"
        storage.upload_file(
            DERIVATIVES_BUCKET,
            thumb_key,
            thumb_path,
            "image/jpeg",
        )
        _record_derivative(
            session,
            asset_id,
            "thumbnail",
            thumb_key,
            "image/jpeg",
            thumb_path,
        )
        keys.append(thumb_key)
    except RuntimeError:
        logger.warning(
            "ffmpeg unavailable; skipping image thumbnail for asset %s",
            asset_id,
        )
    return keys


def _generate_audio_derivatives(
    session: Any,
    storage: StorageService,
    asset_id: str,
    src: str,
    tmp_dir: str,
    base_key: str,
) -> list[str]:
    """generate waveform image for an audio asset."""
    from loom.services.proxy import generate_waveform

    keys: list[str] = []
    try:
        wave_path = str(Path(tmp_dir) / "waveform.jpg")
        generate_waveform(src, wave_path)
        wave_key = f"{base_key}/waveform.jpg"
        storage.upload_file(
            DERIVATIVES_BUCKET,
            wave_key,
            wave_path,
            "image/jpeg",
        )
        _record_derivative(
            session,
            asset_id,
            "waveform",
            wave_key,
            "image/jpeg",
            wave_path,
        )
        keys.append(wave_key)
    except RuntimeError:
        logger.warning(
            "ffmpeg unavailable; skipping waveform for asset %s",
            asset_id,
        )
    return keys


def _record_derivative(
    session: Any,
    asset_id: str,
    deriv_type: str,
    storage_key: str,
    mime_type: str,
    file_path: str,
) -> None:
    """add a derivative record to the session (not yet committed)."""
    from loom.services.hashing import compute_hashes_from_file

    path = Path(file_path)
    file_size = path.stat().st_size
    sha256, _ = compute_hashes_from_file(path)

    deriv = Derivative(
        asset_id=UUID(asset_id),
        type=deriv_type,
        storage_key=storage_key,
        mime_type=mime_type,
        file_size_bytes=file_size,
        sha256_hash=sha256,
    )
    session.add(deriv)


@activity.defn
async def record_derivatives_custody(
    asset_id: str,
) -> None:
    """create chain_of_custody entries for ingest verification.

    idempotent: checks for existing entry before inserting.
    """
    logger.info(
        "recording custody for asset %s",
        asset_id,
    )

    async with get_db_session() as session:
        # fetch asset to get uploaded_by
        result = await session.execute(
            select(Asset).where(Asset.id == UUID(asset_id))
        )
        asset = result.scalar_one_or_none()
        if asset is None:
            msg = f"asset {asset_id} not found"
            raise ValueError(msg)

        # check for existing ingest_verified entry
        existing = await session.execute(
            select(ChainOfCustodyEntry).where(
                ChainOfCustodyEntry.asset_id == UUID(asset_id),
                ChainOfCustodyEntry.action == "ingest_verified",
            )
        )
        if existing.scalar_one_or_none() is not None:
            logger.info(
                "custody already recorded for asset %s",
                asset_id,
            )
            return

        entry = ChainOfCustodyEntry(
            asset_id=UUID(asset_id),
            action="ingest_verified",
            actor_id=asset.uploaded_by,
            detail={
                "action": "ingest_pipeline_complete",
                "sha256_verified": True,
            },
        )
        session.add(entry)
        await session.commit()

    logger.info("custody recorded for asset %s", asset_id)


@activity.defn
async def mark_asset_complete(asset_id: str) -> None:
    """update asset.processing_status to 'complete'.

    idempotent: setting complete on already-complete is a no-op.
    """
    logger.info("marking asset %s as complete", asset_id)

    async with get_db_session() as session:
        result = await session.execute(
            select(Asset).where(Asset.id == UUID(asset_id))
        )
        asset = result.scalar_one_or_none()
        if asset is None:
            msg = f"asset {asset_id} not found"
            raise ValueError(msg)

        asset.processing_status = "complete"
        await session.commit()

    logger.info("asset %s marked complete", asset_id)
