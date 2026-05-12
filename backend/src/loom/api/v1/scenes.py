import asyncio
import logging
from collections.abc import AsyncIterator
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from loom.dependencies import get_db_session, get_storage_backend
from loom.models.scene import Scene
from loom.schemas.scene import (
    SceneListResponse,
    SceneResponse,
)
from loom.security.rbac import (
    get_current_user_id,
    require_authenticated,
)
from loom.services.case import check_case_access
from loom.services.storage_backends import DERIVATIVES_BUCKET, StorageBackend

# thumbnail presigned-url ttl (seconds) — matches asset download.
_THUMBNAIL_URL_TTL_SECONDS = 900

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/cases/{case_id}/assets/{asset_id}/scenes",
    tags=["scenes"],
)


@router.get("", response_model=SceneListResponse)
async def list_scenes(
    case_id: str,
    asset_id: str,
    token_payload: dict[str, Any] = Depends(  # noqa: B008
        require_authenticated
    ),
    session: AsyncIterator[AsyncSession] = Depends(  # noqa: B008
        get_db_session
    ),
) -> SceneListResponse:
    """list detected scenes for an asset (viewer+)."""
    db: AsyncSession = session  # type: ignore[assignment]
    user_id = get_current_user_id(token_payload)

    has_access = await check_case_access(db, case_id, user_id)
    if not has_access:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="insufficient case access",
        )

    result = await db.execute(
        select(Scene)
        .where(Scene.asset_id == UUID(asset_id))
        .order_by(Scene.scene_number)
    )
    scenes = list(result.scalars().all())

    total_duration = sum(s.duration for s in scenes)
    items = [
        SceneResponse(
            id=s.id,
            asset_id=s.asset_id,
            scene_number=s.scene_number,
            start_time=s.start_time,
            end_time=s.end_time,
            start_frame=s.start_frame,
            end_frame=s.end_frame,
            thumbnail_url=None,
            duration=s.duration,
        )
        for s in scenes
    ]

    return SceneListResponse(
        scenes=items,
        total_scenes=len(scenes),
        total_duration=total_duration,
    )


@router.get("/{scene_id}/thumbnail")
async def get_scene_thumbnail(
    case_id: str,
    asset_id: str,
    scene_id: str,
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
    """return a presigned thumbnail url (viewer+)."""
    db: AsyncSession = session  # type: ignore[assignment]
    user_id = get_current_user_id(token_payload)

    has_access = await check_case_access(db, case_id, user_id)
    if not has_access:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="insufficient case access",
        )

    result = await db.execute(select(Scene).where(Scene.id == UUID(scene_id)))
    scene = result.scalar_one_or_none()
    if not scene:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="scene not found",
        )

    if not scene.thumbnail_key:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="no thumbnail available",
        )

    loop = asyncio.get_running_loop()
    url = await loop.run_in_executor(
        None,
        storage.get_presigned_download_url,
        DERIVATIVES_BUCKET,
        scene.thumbnail_key,
        _THUMBNAIL_URL_TTL_SECONDS,
    )
    return {"thumbnail_url": url}


@router.post(
    "/detect",
    status_code=status.HTTP_202_ACCEPTED,
)
async def start_scene_detection(
    case_id: str,
    asset_id: str,
    token_payload: dict[str, Any] = Depends(  # noqa: B008
        require_authenticated
    ),
    session: AsyncIterator[AsyncSession] = Depends(  # noqa: B008
        get_db_session
    ),
) -> dict[str, Any]:
    """start scene detection workflow (editor+).

    returns 202 accepted with the asset id.
    """
    db: AsyncSession = session  # type: ignore[assignment]
    user_id = get_current_user_id(token_payload)

    has_access = await check_case_access(
        db, case_id, user_id, required_role="editor"
    )
    if not has_access:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="insufficient case access",
        )

    workflow_id = f"scene-detect-{asset_id}"
    try:
        from temporalio.client import Client

        from loom.config import get_settings
        from loom.workflows.scene_workflow import (
            SceneDetectionWorkflow,
        )

        settings = get_settings()
        client = await Client.connect(settings.temporal_host)
        await client.start_workflow(
            SceneDetectionWorkflow.run,
            asset_id,
            id=workflow_id,
            task_queue="loom-ingest",
        )
    except Exception:
        logger.error(
            "failed to start scene detection workflow for %s",
            asset_id,
            exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="workflow service unavailable",
        ) from None

    return {
        "status": "accepted",
        "asset_id": asset_id,
        "workflow_id": workflow_id,
    }
