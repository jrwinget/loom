"""import a portable bundle as a new case.

the bundle is streamed to disk, verified (manifest + signature)
synchronously so a tampered or duplicate bundle is rejected before
anything is created, then the empty case is created so its id is
known for status polling and the heavy recreation runs as a
background job.
"""

from __future__ import annotations

import asyncio
import json
import logging
import zipfile
from collections.abc import AsyncIterator
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from loom.config import get_settings
from loom.dependencies import get_db_session
from loom.models.case import Case, CaseMembership
from loom.security.rate_limit import limiter
from loom.security.rbac import get_current_user_id, require_authenticated
from loom.services.portable_bundle import (
    BundleVerificationError,
    verify_bundle,
)
from loom.services.storage_backends import (
    DERIVATIVES_BUCKET,
    StorageBackend,
)
from loom.services.streaming_upload import (
    UploadTooLargeError,
    stream_to_tempfile,
)
from loom.workflows.dispatch import dispatch_workflow
from loom.workflows.shared import get_storage_backend

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/imports", tags=["imports"])


def _upload_limit() -> int:
    return get_settings().max_upload_size_bytes


@router.post("/bundle", status_code=status.HTTP_202_ACCEPTED)
@limiter.limit("10/minute")
async def import_bundle(
    request: Request,
    token_payload: dict[str, Any] = Depends(  # noqa: B008
        require_authenticated
    ),
    session: AsyncIterator[AsyncSession] = Depends(  # noqa: B008
        get_db_session
    ),
    storage: StorageBackend = Depends(  # noqa: B008
        get_storage_backend
    ),
) -> dict[str, Any]:
    """accept a portable bundle, verify it, and start the import.

    returns the new case id, the import workflow id to poll, and the
    signature verification status the operator should be shown.
    """
    db: AsyncSession = session  # type: ignore[assignment]
    user_id = get_current_user_id(token_payload)

    try:
        streamed = await stream_to_tempfile(request, _upload_limit())
    except UploadTooLargeError as err:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=str(err),
        ) from err

    bundle_path = streamed.path
    bundle_sha = streamed.sha256
    try:
        # idempotency: the same bundle must not import twice. check
        # before any expensive verification or case creation.
        existing = await db.scalar(
            select(Case).where(Case.source_bundle_sha256 == bundle_sha)
        )
        if existing is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    "this bundle has already been imported "
                    f"(case {existing.id})"
                ),
            )

        settings = get_settings()
        try:
            signature = verify_bundle(
                bundle_path,
                trusted_keys_pem=settings.bundle_verify_public_keys,
            )
            with zipfile.ZipFile(bundle_path, "r") as zf:
                meta = json.loads(zf.read("bundle.json"))
                case_doc = json.loads(zf.read("data/case.json"))
        except BundleVerificationError as err:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"bundle failed verification: {err}",
            ) from err
        except (zipfile.BadZipFile, KeyError) as err:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="not a valid portable bundle",
            ) from err

        case = await _create_import_case(
            db, case_doc, bundle_sha, user_id, meta
        )
        # move the verified bundle into storage so the background job
        # (which may run out of process on the server profile) can
        # read it; upload_file_move consumes the temp file
        await asyncio.get_running_loop().run_in_executor(
            None,
            storage.upload_file_move,
            DERIVATIVES_BUCKET,
            f"imports/{case.id}/bundle.zip",
            str(bundle_path),
            "application/zip",
        )

        workflow_id = f"bundle-import-{case.id}"
        await dispatch_workflow(
            "bundle_import",
            args=[str(case.id)],
            workflow_id=workflow_id,
        )
    finally:
        bundle_path.unlink(missing_ok=True)

    return {
        "case_id": str(case.id),
        "workflow_id": workflow_id,
        "signature_status": signature.state,
    }


async def _create_import_case(
    db: AsyncSession,
    case_doc: dict[str, Any],
    bundle_sha: str,
    user_id: str,
    meta: dict[str, Any],
) -> Case:
    from uuid import UUID

    async with db.begin_nested():
        name = str(case_doc.get("name") or "Imported case")
        source = meta.get("source_deploy", "another Loom")
        case = Case(
            name=name,
            description=case_doc.get("description"),
            # start closed: the contents arrive via the background job,
            # and an imported case is a record of another deploy's work
            # rather than a live workspace until the operator reopens it
            status="closed",
            created_by=UUID(user_id),
            source_bundle_sha256=bundle_sha,
        )
        db.add(case)
        await db.flush()
        db.add(
            CaseMembership(
                case_id=case.id,
                user_id=UUID(user_id),
                role="owner",
                granted_by=UUID(user_id),
            )
        )
        await db.flush()
    logger.info("created import case %s from %s", case.id, source)
    return case
