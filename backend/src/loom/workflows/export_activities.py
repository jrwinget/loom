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
from loom.models.chain_of_custody import ChainOfCustodyEntry
from loom.models.export_bundle import ExportBundle
from loom.models.user import User
from loom.workflows.shared import get_db_session, get_storage_backend

logger = logging.getLogger(__name__)


@activity.defn
async def build_export(export_id: str) -> str:
    """orchestrate export based on format type.

    each builder reads the persisted request from export.options
    and returns the list of assets whose originals it included (or
    None). handing evidence out is the single most custody-relevant
    act, so an `exported` custody entry per included asset commits
    atomically with the flip to complete — and only then, because a
    failed build must leave no trace in an append-only trail.

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
                exported: list[dict[str, Any]] | None
                if fmt == "pdf_report":
                    exported = await _build_pdf_report(session, export, case_id)
                elif fmt == "json_manifest":
                    exported = await _build_json_manifest(
                        session, export, case_id
                    )
                elif fmt == "court_bundle":
                    exported = await _build_court_bundle(
                        session, export, case_id
                    )
                elif fmt == "portable_bundle":
                    exported = await _build_portable_bundle(
                        session, export, case_id
                    )
                else:
                    exported = await _build_zip_bundle(session, export, case_id)

                for item in exported or []:
                    session.add(
                        ChainOfCustodyEntry(
                            asset_id=item["id"],
                            action="exported",
                            actor_id=export.created_by,
                            detail={
                                "export_id": str(export.id),
                                "format": fmt,
                                "export_name": export.name,
                                "export_sha256": export.sha256_hash,
                                "verified": True,
                                **(
                                    {"exhibit_number": item["exhibit_number"]}
                                    if "exhibit_number" in item
                                    else {}
                                ),
                            },
                        )
                    )
                export.status = "complete"
                await session.commit()
            except Exception:
                logger.exception(
                    "failed to build export %s",
                    export_id,
                )
                # drop anything the builder staged (custody rows are
                # append-only — a failed export must not leave
                # committed "exported" entries behind)
                await session.rollback()
                await session.refresh(export)
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
) -> list[dict[str, Any]] | None:
    """generate pdf report and upload to storage."""
    from loom.services.report import generate_report
    from loom.services.storage_backends import DERIVATIVES_BUCKET

    # a pdf report is inherently the analysis layer; it always
    # renders with the work-product banner
    options = {**(export.options or {}), "work_product": True}
    html, pdf_bytes = await generate_report(session, case_id, options)

    if pdf_bytes:
        sha256 = hashlib.sha256(pdf_bytes).hexdigest()
        key = f"exports/{export.id}/report.pdf"

        try:
            storage = get_storage_backend()
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
    return None


async def _build_json_manifest(
    session: Any,
    export: Any,
    case_id: str,
) -> list[dict[str, Any]] | None:
    """export case data as json manifest."""
    import json

    from loom.services.export import build_export_manifest

    # json_manifest is a full-fidelity data export by contract; the
    # work-product firewall applies to shareable bundles, not to
    # the machine-readable dump. originals cannot ship in a json
    # document either way.
    options = {
        **(export.options or {}),
        "include_analysis": True,
        "include_originals": False,
    }
    manifest = await build_export_manifest(session, case_id, options)
    manifest_json = json.dumps(manifest, indent=2)
    sha256 = hashlib.sha256(manifest_json.encode()).hexdigest()

    export.manifest = manifest
    export.sha256_hash = sha256
    return None


async def _build_zip_bundle(
    session: Any,
    export: Any,
    case_id: str,
) -> list[dict[str, Any]] | None:
    """build zip bundle with manifest and upload."""
    import asyncio

    from loom.services.export import (
        build_export_manifest,
        package_export_bundle,
    )
    from loom.services.storage_backends import DERIVATIVES_BUCKET
    from loom.services.streaming_upload import upload_tmp_dir

    options = export.options or {}
    manifest = await build_export_manifest(session, case_id, options)

    storage = get_storage_backend()
    tmp_path = upload_tmp_dir() / f"export-{export.id}.zip"
    try:
        sha256, exported = package_export_bundle(manifest, storage, tmp_path)
        output_key = f"exports/{export.id}/bundle.zip"
        await asyncio.get_running_loop().run_in_executor(
            None,
            storage.upload_file_move,
            DERIVATIVES_BUCKET,
            output_key,
            str(tmp_path),
            "application/zip",
        )
        export.storage_key = output_key
        export.sha256_hash = sha256
        export.manifest = manifest
        return exported if options.get("include_originals") else None
    finally:
        # upload_file_move consumes the temp file on success; clean
        # up the leftover if the build raised before the move
        tmp_path.unlink(missing_ok=True)


async def _build_portable_bundle(
    session: Any,
    export: Any,
    case_id: str,
) -> list[dict[str, Any]] | None:
    """build a portable bundle (full rows + originals + manifest +
    signature) for import into another Loom, then move it into
    storage. the zip is built in the data-dir temp area so the move
    into the bucket is an atomic rename on the lite filesystem.
    """
    import asyncio

    from loom.config import get_settings
    from loom.services.portable_bundle import build_portable_bundle
    from loom.services.storage_backends import DERIVATIVES_BUCKET
    from loom.services.streaming_upload import upload_tmp_dir

    settings = get_settings()
    storage = get_storage_backend()
    tmp_path = upload_tmp_dir() / f"portable-{export.id}.zip"

    try:
        bundle_sha = await build_portable_bundle(
            session,
            case_id,
            storage,
            tmp_path,
            signing_key_pem=getattr(settings, "bundle_signing_key", None),
        )
        output_key = f"exports/{export.id}/portable_bundle.zip"
        await asyncio.get_running_loop().run_in_executor(
            None,
            storage.upload_file_move,
            DERIVATIVES_BUCKET,
            output_key,
            str(tmp_path),
            "application/zip",
        )
        export.storage_key = output_key
        export.sha256_hash = bundle_sha
        # a portable bundle always carries every original (that is
        # its contract), so every asset gets an exported entry
        from loom.models.asset import Asset as _Asset

        result = await session.execute(
            select(_Asset.id, _Asset.sha256_hash).where(
                _Asset.case_id == export.case_id
            )
        )
        return [
            {"id": row.id, "sha256": row.sha256_hash} for row in result.all()
        ]
    finally:
        # upload_file_move consumes the temp file on success; clean up
        # the leftover if the build raised before the move
        tmp_path.unlink(missing_ok=True)


async def _resolve_preparer(session: Any, user_id: Any) -> str:
    """human name for the bundle cover and § 1746 declaration.

    display_name → email → the raw uuid, so the cover never shows
    an opaque identifier when anything better exists.
    """
    result = await session.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user is None:
        return str(user_id)
    return user.display_name or user.email or str(user_id)


async def _build_court_bundle(
    session: Any,
    export: Any,
    case_id: str,
) -> list[dict[str, Any]] | None:
    """build the court-admissible bundle (cover + declaration +
    exhibit index + custody log + optional report/originals +
    verifier assets + MANIFEST.sha256 + optional signature) and
    upload.
    """
    import asyncio

    from loom.config import get_settings
    from loom.services.court_bundle import build_court_bundle
    from loom.services.storage_backends import DERIVATIVES_BUCKET
    from loom.services.streaming_upload import upload_tmp_dir

    options = export.options or {}
    settings = get_settings()
    storage = get_storage_backend()
    tmp_path = upload_tmp_dir() / f"court-{export.id}.zip"

    try:
        sha256, exported = await build_court_bundle(
            session,
            case_id,
            options,
            storage,
            tmp_path,
            preparer=await _resolve_preparer(session, export.created_by),
            signing_key_pem=getattr(settings, "bundle_signing_key", None),
        )
        output_key = f"exports/{export.id}/court_bundle.zip"
        await asyncio.get_running_loop().run_in_executor(
            None,
            storage.upload_file_move,
            DERIVATIVES_BUCKET,
            output_key,
            str(tmp_path),
            "application/zip",
        )
        export.storage_key = output_key
        export.sha256_hash = sha256
        return exported if options.get("include_originals") else None
    finally:
        tmp_path.unlink(missing_ok=True)
