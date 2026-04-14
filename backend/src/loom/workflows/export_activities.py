"""temporal activities for the export pipeline.

uses shared engine/session instead of per-call engine creation.
"""

import hashlib
import logging
import time
from typing import Any

from sqlalchemy import select
from temporalio import activity

from loom.metrics import ingest_workflow_duration
from loom.models.export_bundle import ExportBundle
from loom.workflows.shared import get_db_session, get_minio_client

logger = logging.getLogger(__name__)


@activity.defn
async def build_export(export_id: str) -> str:
    """orchestrate export based on format type.

    handles three formats:
    - zip: builds manifest and packages into zip bundle
    - pdf_report: generates html/pdf report from case data
    - json_manifest: exports the manifest as json

    idempotent: re-running overwrites the export artifact
    and resets status.
    """
    start = time.monotonic()
    try:
        logger.info("building export bundle %s", export_id)

        async with get_db_session() as session:
            result = await session.execute(
                select(ExportBundle).where(ExportBundle.id == export_id)
            )
            export = result.scalar_one_or_none()
            if not export:
                logger.error("export %s not found", export_id)
                return export_id

            export.status = "processing"
            await session.commit()

            case_id = str(export.case_id)
            fmt = export.format

            try:
                if fmt == "pdf_report":
                    await _build_pdf_report(session, export, case_id)
                elif fmt == "json_manifest":
                    await _build_json_manifest(session, export, case_id)
                else:
                    await _build_zip_bundle(session, export, case_id)

                export.status = "complete"
                await session.commit()
            except Exception:
                logger.exception(
                    "failed to build export %s",
                    export_id,
                )
                export.status = "failed"
                await session.commit()
                raise

        return export_id
    finally:
        duration = time.monotonic() - start
        ingest_workflow_duration.labels(activity="export").observe(duration)


async def _build_pdf_report(
    session: Any,
    export: Any,
    case_id: str,
) -> None:
    """generate pdf report and upload to storage."""
    from loom.services.report import generate_report
    from loom.services.storage import (
        DERIVATIVES_BUCKET,
        StorageService,
    )

    options = export.manifest or {}
    html, pdf_bytes = await generate_report(session, case_id, options)

    if pdf_bytes:
        sha256 = hashlib.sha256(pdf_bytes).hexdigest()
        key = f"exports/{export.id}/report.pdf"

        try:
            storage = StorageService(get_minio_client())
            storage.upload_bytes(
                DERIVATIVES_BUCKET,
                key,
                pdf_bytes,
                "application/pdf",
            )
            export.storage_key = key
            export.sha256_hash = sha256
        except Exception:
            logger.warning("could not upload pdf, storing hash only")
            export.sha256_hash = sha256
    else:
        # html-only fallback
        html_bytes = html.encode("utf-8")
        sha256 = hashlib.sha256(html_bytes).hexdigest()
        export.sha256_hash = sha256


async def _build_json_manifest(
    session: Any,
    export: Any,
    case_id: str,
) -> None:
    """export case data as json manifest."""
    import json

    from loom.services.export import build_export_manifest

    manifest = await build_export_manifest(session, case_id, {})
    manifest_json = json.dumps(manifest, indent=2)
    sha256 = hashlib.sha256(manifest_json.encode()).hexdigest()

    export.manifest = manifest
    export.sha256_hash = sha256


async def _build_zip_bundle(
    session: Any,
    export: Any,
    case_id: str,
) -> None:
    """build zip bundle with manifest and upload."""
    from loom.services.export import (
        build_export_manifest,
        package_export_bundle,
    )
    from loom.services.storage import StorageService

    manifest = await build_export_manifest(session, case_id, {})

    try:
        storage = StorageService(get_minio_client())
        output_key = f"exports/{export.id}/bundle.zip"
        key, sha256 = package_export_bundle(manifest, storage, output_key)
        export.storage_key = key
        export.sha256_hash = sha256
        export.manifest = manifest
    except Exception:
        logger.warning("could not upload zip, storing manifest only")
        export.manifest = manifest
