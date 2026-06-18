"""workflow status polling endpoint.

allows clients to query temporal for the status of a running
or completed workflow.
"""

from collections.abc import AsyncIterator
from datetime import datetime
from typing import Any
from uuid import UUID

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    status,
)
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from loom.config import get_settings
from loom.dependencies import get_db_session
from loom.models.asset import Asset
from loom.models.export_bundle import ExportBundle
from loom.models.ocr import OcrRegion
from loom.models.scene import Scene
from loom.models.transcript import TranscriptSegment
from loom.security.rbac import (
    get_current_user_id,
    require_authenticated,
)
from loom.services.case import check_case_access
from loom.workflows.dispatch import lite_workflow_status

# asset/export persisted states -> the workflow status vocabulary the
# server path reports from temporal. anything not terminal is running.
_TERMINAL = {"complete": "completed", "failed": "failed"}

router = APIRouter(
    prefix="/cases/{case_id}/workflows",
    tags=["workflows"],
)


class WorkflowStatusResponse(BaseModel):
    """response model for workflow status queries."""

    workflow_id: str
    status: str
    start_time: datetime | None = None
    close_time: datetime | None = None
    error: str | None = None


async def _check_access(
    db: AsyncSession,
    case_id: str,
    user_id: str,
) -> None:
    """verify user has case access or raise 403."""
    has_access = await check_case_access(
        db, case_id, user_id, required_role="viewer"
    )
    if not has_access:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="insufficient case access",
        )


@router.get(
    "/{workflow_id}/status",
    response_model=WorkflowStatusResponse,
)
async def get_workflow_status(
    case_id: str,
    workflow_id: str,
    token_payload: dict[str, Any] = Depends(  # noqa: B008
        require_authenticated
    ),
    session: AsyncIterator[AsyncSession] = Depends(  # noqa: B008
        get_db_session
    ),
) -> WorkflowStatusResponse:
    """report workflow execution status.

    server queries temporal; lite has no temporal server, so it
    reports the in-process status (accurate while the app is up)
    and falls back to deriving status from persisted rows.
    """
    db: AsyncSession = session  # type: ignore[assignment]
    user_id = get_current_user_id(token_payload)
    await _check_access(db, case_id, user_id)

    if get_settings().is_lite:
        return await _lite_status(db, workflow_id)

    try:
        from temporalio.client import Client

        settings = get_settings()
        client = await Client.connect(settings.temporal_host)
        handle = client.get_workflow_handle(workflow_id)
        desc = await handle.describe()
    except ImportError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="temporal client not available",
        ) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"workflow not found: {workflow_id}",
        ) from exc

    # map temporal status enum to string
    wf_status = desc.status.name.lower() if desc.status else "unknown"

    # normalize status names
    status_map = {
        "running": "running",
        "completed": "completed",
        "failed": "failed",
        "canceled": "cancelled",
        "cancelled": "cancelled",
        "terminated": "failed",
        "continued_as_new": "running",
        "timed_out": "failed",
    }
    normalized = status_map.get(wf_status, wf_status)

    # extract error from failure info if available
    error_msg: str | None = None
    if normalized == "failed":
        try:
            # temporal sdk exposes failure in close event
            if hasattr(desc, "failure") and desc.failure:
                error_msg = str(desc.failure.message)
        except Exception:
            error_msg = "workflow failed (details unavailable)"

    return WorkflowStatusResponse(
        workflow_id=workflow_id,
        status=normalized,
        start_time=desc.start_time,
        close_time=desc.close_time,
        error=error_msg,
    )


async def _lite_status(
    db: AsyncSession,
    workflow_id: str,
) -> WorkflowStatusResponse:
    """report in-process status, deriving from db after a restart."""
    in_memory = lite_workflow_status(workflow_id)
    if in_memory is not None:
        return WorkflowStatusResponse(
            workflow_id=workflow_id,
            status=in_memory,
        )

    derived = await _derive_status_from_db(db, workflow_id)
    if derived is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"workflow not found: {workflow_id}",
        )
    return WorkflowStatusResponse(workflow_id=workflow_id, status=derived)


async def _derive_status_from_db(
    db: AsyncSession,
    workflow_id: str,
) -> str | None:
    """map a workflow id back to the status of the row it produced.

    the id prefix encodes the kind and the target row id (e.g.
    ``ocr-<asset_id>``, ``export-<export_id>``); presence of the
    produced rows means the in-process run finished.
    """
    if workflow_id.startswith("url-ingest-"):
        return await _asset_status(db, workflow_id[len("url-ingest-") :])
    if workflow_id.startswith("ingest-"):
        return await _asset_status(db, workflow_id[len("ingest-") :])
    if workflow_id.startswith("export-"):
        export = await db.get(ExportBundle, workflow_id[len("export-") :])
        if export is None:
            return None
        return _TERMINAL.get(export.status, "running")
    if workflow_id.startswith("scene-detect-"):
        return await _rows_exist(db, Scene, workflow_id[len("scene-detect-") :])
    if workflow_id.startswith("ocr-"):
        return await _rows_exist(db, OcrRegion, workflow_id[len("ocr-") :])
    if workflow_id.startswith("transcribe-"):
        return await _rows_exist(
            db, TranscriptSegment, workflow_id[len("transcribe-") :]
        )
    return None


async def _asset_status(db: AsyncSession, asset_id: str) -> str | None:
    asset = await db.get(Asset, UUID(asset_id))
    if asset is None:
        return None
    return _TERMINAL.get(asset.processing_status, "running")


async def _rows_exist(db: AsyncSession, model: Any, asset_id: str) -> str:
    count = await db.scalar(
        select(func.count())
        .select_from(model)
        .where(model.asset_id == UUID(asset_id))
    )
    return "completed" if count else "running"
