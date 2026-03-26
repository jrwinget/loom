import logging
from typing import Any

from temporalio import activity

logger = logging.getLogger(__name__)


@activity.defn
async def verify_asset_hash(asset_id: str) -> bool:
    """download asset from minio, re-hash, compare to db.

    currently a stub that returns True. full implementation
    requires a running minio instance.
    """
    logger.info("verifying hash for asset %s", asset_id)
    # TODO: implement when minio is running
    # 1. fetch asset record from db
    # 2. download from minio to temp file
    # 3. compute sha256/sha512
    # 4. compare to asset.sha256_hash / sha512_hash
    return True


@activity.defn
async def extract_asset_metadata(asset_id: str) -> dict[str, Any]:
    """download file, extract metadata, store in db.

    currently a stub that returns empty metadata.
    """
    logger.info("extracting metadata for asset %s", asset_id)
    # TODO: full implementation
    # 1. fetch asset from db
    # 2. download from minio to temp file
    # 3. call extract_metadata_from_file
    # 4. update asset.metadata_raw and metadata_extracted
    return {"status": "stub", "asset_id": asset_id}


@activity.defn
async def generate_asset_proxies(
    asset_id: str,
) -> list[str]:
    """generate derivative proxies based on media type.

    currently a stub that returns an empty list.
    """
    logger.info("generating proxies for asset %s", asset_id)
    # TODO: full implementation
    # 1. fetch asset from db
    # 2. download original from minio to temp dir
    # 3. generate proxy/thumbnails based on media_type
    # 4. upload derivatives to minio
    # 5. create Derivative records in db
    return []


@activity.defn
async def record_derivatives_custody(
    asset_id: str,
) -> None:
    """create chain_of_custody entries for derivatives.

    currently a stub.
    """
    logger.info(
        "recording derivative custody for asset %s",
        asset_id,
    )
    # TODO: full implementation
    # 1. fetch all derivatives for asset
    # 2. create ChainOfCustodyEntry for each


@activity.defn
async def mark_asset_complete(asset_id: str) -> None:
    """update asset.processing_status to 'complete'.

    currently a stub.
    """
    logger.info("marking asset %s as complete", asset_id)
    # TODO: full implementation
    # 1. fetch asset from db
    # 2. set processing_status = "complete"
    # 3. commit
