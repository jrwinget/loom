import logging
from typing import Any

from temporalio import activity

logger = logging.getLogger(__name__)


@activity.defn
async def prepare_ocr_input(  # pragma: no cover
    asset_id: str,
) -> dict[str, Any]:
    """prepare images for ocr processing.

    for video assets, extracts key frames. for images,
    returns the asset path directly. currently a stub.
    """
    logger.info("preparing ocr input for asset %s", asset_id)
    # TODO: full implementation
    # 1. fetch asset from db
    # 2. download from minio to temp dir
    # 3. if video, call extract_key_frames
    # 4. return dict with image paths
    return {"status": "stub", "asset_id": asset_id}


@activity.defn
async def run_ocr(  # pragma: no cover
    asset_id: str,
) -> dict[str, Any]:
    """run ocr on prepared images.

    currently a stub that returns empty results.
    """
    logger.info("running ocr for asset %s", asset_id)
    # TODO: full implementation
    # 1. load prepared image paths from previous step
    # 2. call run_ocr_on_image for each
    # 3. aggregate results
    return {"status": "stub", "asset_id": asset_id}


@activity.defn
async def store_ocr_results(  # pragma: no cover
    asset_id: str,
) -> dict[str, Any]:
    """store ocr results in the database.

    currently a stub.
    """
    logger.info("storing ocr results for asset %s", asset_id)
    # TODO: full implementation
    # 1. fetch ocr results from previous step
    # 2. call store_ocr_regions
    return {"status": "stub", "asset_id": asset_id}
