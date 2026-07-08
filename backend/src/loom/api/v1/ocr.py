import logging
from collections.abc import AsyncIterator
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from loom.dependencies import get_db_session
from loom.models.ocr import OcrRegion
from loom.schemas.ocr import OcrRegionResponse, OcrResultResponse
from loom.security.rbac import get_current_user_id, require_authenticated
from loom.services.case import check_case_access
from loom.services.search import _ilike_pattern
from loom.workflows.dispatch import dispatch_workflow

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/cases/{case_id}/assets/{asset_id}/ocr",
    tags=["ocr"],
)


@router.get("", response_model=OcrResultResponse)
async def get_ocr_regions(
    case_id: str,
    asset_id: str,
    text: str | None = Query(None, description="text search"),
    min_confidence: float | None = Query(None, ge=0.0, le=1.0),
    frame_start: int | None = Query(None, ge=0),
    frame_end: int | None = Query(None, ge=0),
    token_payload: dict[str, Any] = Depends(  # noqa: B008
        require_authenticated
    ),
    session: AsyncIterator[AsyncSession] = Depends(  # noqa: B008
        get_db_session
    ),
) -> OcrResultResponse:
    """get ocr regions for an asset (requires viewer+)."""
    db: AsyncSession = session  # type: ignore[assignment]
    user_id = get_current_user_id(token_payload)

    has_access = await check_case_access(db, case_id, user_id)
    if not has_access:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="insufficient case access",
        )

    query = select(OcrRegion).where(OcrRegion.asset_id == asset_id)

    if text is not None:
        query = query.where(OcrRegion.text.ilike(_ilike_pattern(text)))
    if min_confidence is not None:
        query = query.where(OcrRegion.confidence >= min_confidence)
    if frame_start is not None:
        query = query.where(OcrRegion.frame_number >= frame_start)
    if frame_end is not None:
        query = query.where(OcrRegion.frame_number <= frame_end)

    query = query.order_by(OcrRegion.created_at)
    result = await db.execute(query)
    regions = list(result.scalars().all())

    # detect unique languages
    languages = sorted({r.language for r in regions if r.language is not None})

    items = [
        OcrRegionResponse(
            id=r.id,
            asset_id=r.asset_id,
            frame_number=r.frame_number,
            timestamp=r.timestamp,
            bounding_box=r.bounding_box,
            text=r.text,
            confidence=r.confidence,
            language=r.language,
            created_at=r.created_at,
        )
        for r in regions
    ]

    return OcrResultResponse(
        regions=items,
        total_regions=len(items),
        languages_detected=languages,
    )


@router.post(
    "/run",
    status_code=status.HTTP_202_ACCEPTED,
)
async def start_ocr_workflow(
    case_id: str,
    asset_id: str,
    token_payload: dict[str, Any] = Depends(  # noqa: B008
        require_authenticated
    ),
    session: AsyncIterator[AsyncSession] = Depends(  # noqa: B008
        get_db_session
    ),
) -> dict[str, Any]:
    """start ocr workflow for an asset (requires editor+).

    returns 202 accepted with workflow id.
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

    workflow_id = f"ocr-{asset_id}"
    try:
        await dispatch_workflow("ocr", args=[asset_id], workflow_id=workflow_id)
    except Exception:
        logger.error(
            "failed to start ocr workflow for %s",
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
