import hashlib
import logging
from typing import Any

from temporalio import activity

logger = logging.getLogger(__name__)


@activity.defn
async def build_export(export_id: str) -> str:
    """orchestrate export based on format type.

    handles three formats:
    - zip: builds manifest and packages into zip bundle
    - pdf_report: generates html/pdf report from case data
    - json_manifest: exports the manifest as json

    currently implemented with inline db session creation.
    requires running db and minio for full operation.
    """
    logger.info("building export bundle %s", export_id)

    # lazy imports to avoid circular deps and allow temporal
    # sandboxing to pass through
    from loom.config import get_settings
    from loom.models.export_bundle import ExportBundle

    settings = get_settings()

    # create async db session
    from sqlalchemy.ext.asyncio import (
        AsyncSession,
        create_async_engine,
    )

    engine = create_async_engine(settings.database_url)

    try:
        async with AsyncSession(engine) as session:
            from sqlalchemy import select

            # fetch export record
            result = await session.execute(
                select(ExportBundle).where(ExportBundle.id == export_id)
            )
            export = result.scalar_one_or_none()
            if not export:
                logger.error("export %s not found", export_id)
                return export_id

            # update status to processing
            export.status = "processing"
            await session.commit()

            case_id = str(export.case_id)
            fmt = export.format

            if fmt == "pdf_report":
                await _build_pdf_report(session, export, case_id)
            elif fmt == "json_manifest":
                await _build_json_manifest(session, export, case_id)
            else:
                # default: zip bundle
                await _build_zip_bundle(session, export, case_id)

            export.status = "complete"
            await session.commit()

    except Exception:
        logger.exception("failed to build export %s", export_id)
        # mark as failed if possible
        try:
            async with AsyncSession(engine) as err_session:
                from sqlalchemy import select as sel2

                res = await err_session.execute(
                    sel2(ExportBundle).where(ExportBundle.id == export_id)
                )
                exp = res.scalar_one_or_none()
                if exp:
                    exp.status = "failed"
                    await err_session.commit()
        except Exception:
            logger.exception(
                "could not mark export %s as failed",
                export_id,
            )
        raise
    finally:
        await engine.dispose()

    return export_id


async def _build_pdf_report(
    session: Any,
    export: Any,
    case_id: str,
) -> None:
    """generate pdf report and upload to storage."""
    from loom.services.report import generate_report

    # extract options from export manifest if available
    options = export.manifest or {}

    html, pdf_bytes = await generate_report(session, case_id, options)

    if pdf_bytes:
        sha256 = hashlib.sha256(pdf_bytes).hexdigest()
        key = f"exports/{export.id}/report.pdf"

        # upload to storage
        try:
            from loom.config import get_settings
            from loom.services.storage import (
                DERIVATIVES_BUCKET,
                StorageService,
            )

            settings = get_settings()
            from minio import Minio

            minio = Minio(
                settings.minio_endpoint,
                access_key=settings.minio_access_key,
                secret_key=settings.minio_secret_key,
                secure=settings.minio_secure,
            )
            storage = StorageService(minio)
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
    from loom.config import get_settings
    from loom.services.export import (
        build_export_manifest,
        package_export_bundle,
    )
    from loom.services.storage import StorageService

    manifest = await build_export_manifest(session, case_id, {})

    try:
        from minio import Minio

        settings = get_settings()
        minio = Minio(
            settings.minio_endpoint,
            access_key=settings.minio_access_key,
            secret_key=settings.minio_secret_key,
            secure=settings.minio_secure,
        )
        storage = StorageService(minio)
        output_key = f"exports/{export.id}/bundle.zip"
        key, sha256 = package_export_bundle(manifest, storage, output_key)
        export.storage_key = key
        export.sha256_hash = sha256
        export.manifest = manifest
    except Exception:
        logger.warning("could not upload zip, storing manifest only")
        export.manifest = manifest
