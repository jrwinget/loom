import asyncio
import logging
from collections.abc import AsyncIterator
from typing import Any

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Query,
    status,
)
from minio import Minio
from sqlalchemy.ext.asyncio import AsyncSession

from loom.dependencies import get_db_session, get_minio_client
from loom.schemas.export_bundle import (
    ExportCreate,
    ExportListResponse,
    ExportResponse,
)
from loom.security.rbac import (
    get_current_user_id,
    require_authenticated,
)
from loom.services.case import check_case_access
from loom.services.export import (
    create_export_record,
    get_export,
    list_exports,
)
from loom.services.storage import (
    DERIVATIVES_BUCKET,
    StorageService,
)

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/cases/{case_id}/exports",
    tags=["exports"],
)


async def _check_access(
    db: AsyncSession,
    case_id: str,
    user_id: str,
    required_role: str = "viewer",
) -> None:
    """verify user has case access or raise 403."""
    has_access = await check_case_access(
        db, case_id, user_id, required_role=required_role
    )
    if not has_access:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="insufficient case access",
        )


@router.post(
    "",
    response_model=ExportResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_export_endpoint(
    case_id: str,
    body: ExportCreate,
    token_payload: dict[str, Any] = Depends(  # noqa: B008
        require_authenticated
    ),
    session: AsyncIterator[AsyncSession] = Depends(  # noqa: B008
        get_db_session
    ),
) -> ExportResponse:
    """create an export bundle (editor+)."""
    db: AsyncSession = session  # type: ignore[assignment]
    user_id = get_current_user_id(token_payload)
    await _check_access(db, case_id, user_id, "editor")

    export = await create_export_record(
        db, case_id, body.name, body.format, user_id
    )

    try:
        from temporalio.client import Client

        from loom.config import get_settings

        settings = get_settings()
        temporal = await Client.connect(settings.temporal_host)
        await temporal.start_workflow(
            "ExportWorkflow",
            str(export.id),
            id=f"export-{export.id}",
            task_queue="loom-ingest",
        )
    except Exception:
        logger.error(
            "failed to start export workflow for %s",
            export.id,
            exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="workflow service unavailable",
        ) from None

    return ExportResponse.model_validate(export)


@router.get("", response_model=ExportListResponse)
async def list_exports_endpoint(
    case_id: str,
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    token_payload: dict[str, Any] = Depends(  # noqa: B008
        require_authenticated
    ),
    session: AsyncIterator[AsyncSession] = Depends(  # noqa: B008
        get_db_session
    ),
) -> ExportListResponse:
    """list exports for a case (viewer+)."""
    db: AsyncSession = session  # type: ignore[assignment]
    user_id = get_current_user_id(token_payload)
    await _check_access(db, case_id, user_id)

    exports, total = await list_exports(db, case_id, skip, limit)
    items = [ExportResponse.model_validate(e) for e in exports]
    return ExportListResponse(items=items, total=total)


@router.get(
    "/{export_id}",
    response_model=ExportResponse,
)
async def get_export_endpoint(
    case_id: str,
    export_id: str,
    token_payload: dict[str, Any] = Depends(  # noqa: B008
        require_authenticated
    ),
    session: AsyncIterator[AsyncSession] = Depends(  # noqa: B008
        get_db_session
    ),
    minio_client: Minio = Depends(  # noqa: B008
        get_minio_client
    ),
) -> ExportResponse:
    """get export detail with download url if complete."""
    db: AsyncSession = session  # type: ignore[assignment]
    user_id = get_current_user_id(token_payload)
    await _check_access(db, case_id, user_id)

    export = await get_export(db, export_id)
    if not export or str(export.case_id) != case_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="export not found",
        )

    resp = ExportResponse.model_validate(export)

    # generate download url if export is complete
    if export.status == "complete" and export.storage_key:
        storage = StorageService(minio_client)
        loop = asyncio.get_running_loop()
        url = await loop.run_in_executor(
            None,
            storage.get_presigned_download_url,
            DERIVATIVES_BUCKET,
            export.storage_key,
            900,
        )
        resp.storage_key = url

    return resp
