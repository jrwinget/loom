"""workflow status polling endpoint.

allows clients to query temporal for the status of a running
or completed workflow.
"""

from collections.abc import AsyncIterator
from datetime import datetime
from typing import Any

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    status,
)
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from loom.dependencies import get_db_session
from loom.security.rbac import (
    get_current_user_id,
    require_authenticated,
)
from loom.services.case import check_case_access

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
    """query temporal for workflow execution status."""
    db: AsyncSession = session  # type: ignore[assignment]
    user_id = get_current_user_id(token_payload)
    await _check_access(db, case_id, user_id)

    try:
        from temporalio.client import Client

        from loom.config import get_settings

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
