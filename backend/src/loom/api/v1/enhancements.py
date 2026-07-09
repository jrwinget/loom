"""deterministic clarity-assist enhancement endpoints.

surfaces the enhancement service (classical ffmpeg filters only, no
ai / super-resolution) to the review ui: suggest starting parameters
from a measured sample, dispatch an enhancement run, and list the
produced derivatives with full provenance. suggestions are never
auto-applied — the reviewer confirms before a derivative is made.
"""

import asyncio
import json
import logging
import tempfile
from collections.abc import AsyncIterator
from dataclasses import asdict
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from loom.dependencies import get_db_session, get_storage_backend
from loom.models.asset import Asset
from loom.models.derivative import Derivative
from loom.schemas.enhancement import (
    EnhancementCreatedResponse,
    EnhancementDerivativeResponse,
    EnhancementListResponse,
    EnhancementParamsSchema,
    EnhancementSuggestResponse,
)
from loom.security.rbac import get_current_user_id, require_authenticated
from loom.services.asset import get_asset as get_asset_svc
from loom.services.case import check_case_access
from loom.services.engines import EngineUnavailableError
from loom.services.enhancement import (
    EnhancementParams,
    VideoStats,
    analyze_video,
    suggest_params,
)
from loom.services.storage_backends import (
    DERIVATIVES_BUCKET,
    ORIGINALS_BUCKET,
    StorageBackend,
)
from loom.workflows.dispatch import dispatch_workflow

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/cases/{case_id}/assets/{asset_id}/enhancements",
    tags=["enhancements"],
)

# media kinds the deterministic filters apply to; audio/document
# assets have no visual signal to enhance
_ENHANCEABLE = ("video", "image")


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


async def _require_asset(
    db: AsyncSession,
    case_id: str,
    asset_id: str,
) -> Asset:
    """load the case-scoped asset or raise 404."""
    asset = await get_asset_svc(db, case_id, asset_id)
    if not asset:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="asset not found",
        )
    return asset


@router.post(
    "",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=EnhancementCreatedResponse,
)
async def create_enhancement(
    case_id: str,
    asset_id: str,
    body: EnhancementParamsSchema,
    token_payload: dict[str, Any] = Depends(  # noqa: B008
        require_authenticated
    ),
    session: AsyncIterator[AsyncSession] = Depends(  # noqa: B008
        get_db_session
    ),
) -> EnhancementCreatedResponse:
    """dispatch a deterministic enhancement run (editor+).

    returns 202 with the workflow id to poll. each run produces a new
    derivative, so the id carries a uuid suffix to stay unique.
    """
    db: AsyncSession = session  # type: ignore[assignment]
    user_id = get_current_user_id(token_payload)
    await _check_access(db, case_id, user_id, "editor")

    asset = await _require_asset(db, case_id, asset_id)
    if asset.media_type not in _ENHANCEABLE:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "enhancement is only available for video and image "
                f"assets, not {asset.media_type}"
            ),
        )

    # revalidate through the service dataclass so the range contract
    # has a single source of truth even if the schema drifts
    try:
        params = EnhancementParams(**body.model_dump())
    except ValueError as err:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(err),
        ) from err

    workflow_id = f"enhance-{asset_id}-{uuid4().hex[:8]}"
    params_json = json.dumps(asdict(params))
    try:
        await dispatch_workflow(
            "enhancement",
            args=[asset_id, params_json],
            workflow_id=workflow_id,
        )
    except Exception:
        logger.error(
            "failed to start enhancement workflow for %s",
            asset_id,
            exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="workflow service unavailable",
        ) from None

    return EnhancementCreatedResponse(
        workflow_id=workflow_id,
        status="queued",
        params=body,
    )


@router.get("", response_model=EnhancementListResponse)
async def list_enhancements(
    case_id: str,
    asset_id: str,
    token_payload: dict[str, Any] = Depends(  # noqa: B008
        require_authenticated
    ),
    session: AsyncIterator[AsyncSession] = Depends(  # noqa: B008
        get_db_session
    ),
    storage: StorageBackend = Depends(  # noqa: B008
        get_storage_backend
    ),
) -> EnhancementListResponse:
    """list the asset's enhancement derivatives (viewer+)."""
    db: AsyncSession = session  # type: ignore[assignment]
    user_id = get_current_user_id(token_payload)
    await _check_access(db, case_id, user_id)
    await _require_asset(db, case_id, asset_id)

    result = await db.execute(
        select(Derivative)
        .where(
            Derivative.asset_id == UUID(asset_id),
            Derivative.type == "enhancement",
        )
        .order_by(Derivative.created_at.desc())
    )
    derivatives = list(result.scalars().all())

    loop = asyncio.get_running_loop()
    items: list[EnhancementDerivativeResponse] = []
    for deriv in derivatives:
        url = await loop.run_in_executor(
            None,
            storage.get_presigned_download_url,
            DERIVATIVES_BUCKET,
            deriv.storage_key,
            900,
        )
        items.append(
            EnhancementDerivativeResponse(
                id=deriv.id,
                generation_params=deriv.generation_params,
                created_at=deriv.created_at,
                download_url=url,
            )
        )

    return EnhancementListResponse(enhancements=items)


@router.get("/suggest", response_model=EnhancementSuggestResponse)
async def suggest_enhancement(
    case_id: str,
    asset_id: str,
    token_payload: dict[str, Any] = Depends(  # noqa: B008
        require_authenticated
    ),
    session: AsyncIterator[AsyncSession] = Depends(  # noqa: B008
        get_db_session
    ),
    storage: StorageBackend = Depends(  # noqa: B008
        get_storage_backend
    ),
) -> EnhancementSuggestResponse:
    """suggest starting parameters from a measured sample (viewer+).

    analyses only the leading seconds of the video, so it is safe to
    run synchronously. the reasons explain which threshold fired for
    each non-neutral suggestion.
    """
    db: AsyncSession = session  # type: ignore[assignment]
    user_id = get_current_user_id(token_payload)
    await _check_access(db, case_id, user_id)

    asset = await _require_asset(db, case_id, asset_id)
    if asset.media_type != "video":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "suggestions require a video asset; image analysis "
                "is not supported"
            ),
        )

    stats = await _analyze(storage, asset)
    params = suggest_params(stats)
    return EnhancementSuggestResponse(
        params=EnhancementParamsSchema(**asdict(params)),
        reasons=_suggestion_reasons(stats, params),
    )


async def _analyze(storage: StorageBackend, asset: Asset) -> VideoStats:
    """download the original and measure a leading sample.

    maps a missing ffmpeg to 503 with the remedy and unmeasurable
    footage to 422; nothing is fabricated on failure.
    """
    loop = asyncio.get_running_loop()
    with tempfile.TemporaryDirectory(prefix="loom_suggest_") as tmp_dir:
        suffix = Path(asset.original_filename).suffix
        src = str(Path(tmp_dir) / f"original{suffix}")
        await loop.run_in_executor(
            None,
            storage.download_file,
            ORIGINALS_BUCKET,
            asset.storage_key,
            src,
        )
        try:
            return await loop.run_in_executor(None, analyze_video, src)
        except EngineUnavailableError as err:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=err.remedy,
            ) from err
        except ValueError as err:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=str(err),
            ) from err


def _suggestion_reasons(
    stats: VideoStats,
    params: EnhancementParams,
) -> list[str]:
    """human rationale for each non-neutral suggested parameter."""
    reasons: list[str] = []
    if params.brightness != 0.0:
        reasons.append(
            f"footage is dark (luma avg {stats.yavg:.0f}) -> "
            f"brightness +{params.brightness}"
        )
    if params.gamma != 1.0:
        reasons.append(
            f"footage is very dark (luma avg {stats.yavg:.0f}) -> "
            f"gamma {params.gamma}"
        )
    if params.contrast != 1.0:
        reasons.append(
            f"luma range is flat ({stats.ymin:.0f}-{stats.ymax:.0f}) -> "
            f"contrast {params.contrast}"
        )
    if params.denoise > 0:
        reasons.append(
            f"frame-to-frame noise is high (luma diff {stats.ydif:.1f}) "
            f"-> denoise {params.denoise}"
        )
    if params.deinterlace:
        reasons.append("interlacing detected -> deinterlace (yadif)")
    if params.scale_factor > 1:
        reasons.append(
            f"low resolution ({stats.height}p) -> upscale "
            f"{params.scale_factor}x (lanczos)"
        )
    return reasons
