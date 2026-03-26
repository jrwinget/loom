import logging

from temporalio import activity

logger = logging.getLogger(__name__)


@activity.defn
async def build_export(export_id: str) -> str:
    """orchestrate manifest building, zip creation, and upload.

    steps:
    1. fetch export record from db
    2. build manifest from case data
    3. package into zip and upload to minio
    4. update export record with hash and storage_key
    5. mark as complete (or failed on error)

    currently a stub that marks the export as complete.
    full implementation requires running db and minio.
    """
    logger.info("building export bundle %s", export_id)
    # TODO: full implementation
    # 1. get async db session
    # 2. fetch export record
    # 3. update status to "processing"
    # 4. build_export_manifest(session, case_id, options)
    # 5. package_export_bundle(manifest, storage, key)
    # 6. update export record with storage_key, sha256, manifest
    # 7. set status = "complete"
    return export_id
