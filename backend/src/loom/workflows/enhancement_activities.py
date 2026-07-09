"""temporal activity for the clarity-assist enhancement pipeline.

runs the deterministic ffmpeg enhancement service on an asset's
original and records the result as a ``type="enhancement"``
derivative with full parameter provenance, so every output is
reproducible byte-for-byte from its recorded parameters.

no output is fabricated on failure: a missing ffmpeg surfaces as
EngineUnavailableError (the service maps it), which the runner
records as a failed job instead of an empty derivative.
"""

import json
import logging
import tempfile
import time
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from temporalio import activity

from loom.metrics import ingest_workflow_duration
from loom.models.asset import Asset
from loom.models.derivative import Derivative
from loom.services.enhancement import (
    EnhancementParams,
    enhance_image,
    enhance_video,
    enhancement_provenance,
)
from loom.services.hashing import compute_hashes_from_file
from loom.services.storage_backends import (
    DERIVATIVES_BUCKET,
    ORIGINALS_BUCKET,
    StorageBackend,
)
from loom.services.streaming_upload import upload_tmp_dir
from loom.workflows.shared import get_db_session, get_storage_backend

logger = logging.getLogger(__name__)


@activity.defn
async def enhance_asset(asset_id: str, params_json: str) -> str:
    """produce a deterministically enhanced derivative of an asset.

    ``params_json`` is a json object of the EnhancementParams fields.
    returns the new derivative id. each call creates a fresh
    derivative, so no idempotency guard is needed.
    """
    start = time.monotonic()
    try:
        params = EnhancementParams(**json.loads(params_json))
        storage = get_storage_backend()
        async with get_db_session() as session:
            asset = await _require_asset(session, asset_id)
            derivative_id = _produce_enhancement(
                session, storage, asset, asset_id, params
            )
            await session.commit()
        logger.info(
            "enhanced asset %s -> derivative %s",
            asset_id,
            derivative_id,
        )
        return str(derivative_id)
    finally:
        duration = time.monotonic() - start
        ingest_workflow_duration.labels(activity="enhancement").observe(
            duration
        )


async def _require_asset(session: AsyncSession, asset_id: str) -> Asset:
    """load the asset or raise so the run fails visibly."""
    result = await session.execute(
        select(Asset).where(Asset.id == UUID(asset_id))
    )
    asset = result.scalar_one_or_none()
    if asset is None:
        msg = f"asset not found: {asset_id}"
        raise ValueError(msg)
    return asset


def _produce_enhancement(
    session: Any,
    storage: StorageBackend,
    asset: Asset,
    asset_id: str,
    params: EnhancementParams,
) -> UUID:
    """download the original, enhance it, and record the derivative.

    the output is written to the buckets temp dir so the move into
    DERIVATIVES is an atomic rename on the lite filesystem; hash and
    size are read before the move consumes the file.
    """
    derivative_id = uuid4()
    ext = _derivative_ext(asset)
    mime = _derivative_mime(asset)
    key = f"enhancements/{asset_id}/{derivative_id}.{ext}"
    out_path = upload_tmp_dir() / f"enhance-{derivative_id}.{ext}"

    try:
        with tempfile.TemporaryDirectory(prefix="loom_enhance_") as tmp_dir:
            suffix = Path(asset.original_filename).suffix
            src = str(Path(tmp_dir) / f"original{suffix}")
            storage.download_file(ORIGINALS_BUCKET, asset.storage_key, src)
            # a missing ffmpeg raises here; nothing is uploaded or
            # recorded, so the caller never persists a partial result
            _enhance_by_type(asset.media_type, src, str(out_path), params)
            sha256, _ = compute_hashes_from_file(out_path)
            size = out_path.stat().st_size
            storage.upload_file_move(
                DERIVATIVES_BUCKET, key, str(out_path), mime
            )
    finally:
        # upload_file_move consumes the temp file on success; reap the
        # leftover if enhancement raised before the move
        out_path.unlink(missing_ok=True)

    session.add(
        Derivative(
            id=derivative_id,
            asset_id=UUID(asset_id),
            type="enhancement",
            storage_key=key,
            mime_type=mime,
            file_size_bytes=size,
            sha256_hash=sha256,
            generation_params=enhancement_provenance(params),
        )
    )
    return derivative_id


def _enhance_by_type(
    media_type: str,
    src: str,
    out: str,
    params: EnhancementParams,
) -> None:
    """dispatch to the video or image enhancement path."""
    if media_type == "video":
        enhance_video(src, out, params)
    elif media_type == "image":
        enhance_image(src, out, params)
    else:
        msg = f"enhancement supports video and image, not {media_type}"
        raise ValueError(msg)


def _derivative_ext(asset: Asset) -> str:
    """file extension for the enhanced derivative."""
    if asset.media_type == "video":
        # enhance_video always re-encodes to h.264/mp4
        return "mp4"
    return Path(asset.original_filename).suffix.lstrip(".") or "png"


def _derivative_mime(asset: Asset) -> str:
    """mime type for the enhanced derivative."""
    if asset.media_type == "video":
        return "video/mp4"
    return asset.mime_type
