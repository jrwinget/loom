import logging

from temporalio import activity

logger = logging.getLogger(__name__)


@activity.defn
async def detect_asset_scenes(asset_id: str) -> list[dict]:
    """download video from minio and run scene detection.

    currently a stub that returns an empty list. full
    implementation requires running minio instance.
    """
    logger.info("detecting scenes for asset %s", asset_id)
    # TODO: full implementation
    # 1. fetch asset record from db
    # 2. download from minio to temp file
    # 3. call detect_scenes(temp_path, threshold)
    # 4. cache results for next activity
    return []


@activity.defn
async def generate_scene_thumbs(
    asset_id: str,
) -> list[str]:
    """generate thumbnail images for detected scenes.

    currently a stub that returns an empty list.
    """
    logger.info(
        "generating scene thumbnails for asset %s",
        asset_id,
    )
    # TODO: full implementation
    # 1. fetch asset from db, download video
    # 2. call generate_scene_thumbnails(path, scenes, dir)
    # 3. upload thumbnails to minio
    # 4. return list of storage keys
    return []


@activity.defn
async def store_scene_results(asset_id: str) -> None:
    """persist detected scene records to the database.

    currently a stub.
    """
    logger.info("storing scene results for asset %s", asset_id)
    # TODO: full implementation
    # 1. get async db session
    # 2. call store_scenes(session, asset_id, scenes)
    # 3. commit
