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
from sqlalchemy.ext.asyncio import AsyncSession

from loom.dependencies import get_db_session
from loom.schemas.transcript import (
    TranscriptResponse,
    TranscriptSegmentResponse,
)
from loom.security.rbac import (
    get_current_user_id,
    require_authenticated,
)
from loom.services.case import check_case_access
from loom.services.transcription import (
    get_transcript_segments,
)

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/cases/{case_id}/assets/{asset_id}",
    tags=["transcripts"],
)


@router.get(
    "/transcript",
    response_model=TranscriptResponse,
)
async def get_transcript_endpoint(
    case_id: str,
    asset_id: str,
    speaker: str | None = Query(None),
    start_time: float | None = Query(None, ge=0),
    end_time: float | None = Query(None, ge=0),
    token_payload: dict[str, Any] = Depends(  # noqa: B008
        require_authenticated
    ),
    session: AsyncIterator[AsyncSession] = Depends(  # noqa: B008
        get_db_session
    ),
) -> TranscriptResponse:
    """get transcript segments for an asset (viewer+)."""
    db: AsyncSession = session  # type: ignore[assignment]
    user_id = get_current_user_id(token_payload)

    has_access = await check_case_access(db, case_id, user_id)
    if not has_access:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="insufficient case access",
        )

    segments = await get_transcript_segments(
        db,
        asset_id,
        speaker=speaker,
        start_time=start_time,
        end_time=end_time,
    )

    items = [
        TranscriptSegmentResponse(
            id=s.id,
            asset_id=s.asset_id,
            speaker_label=s.speaker_label,
            start_time=s.start_time,
            end_time=s.end_time,
            text=s.text,
            confidence=s.confidence,
            language=s.language,
        )
        for s in segments
    ]

    # compute aggregate info
    total_duration = 0.0
    if segments:
        total_duration = max(s.end_time for s in segments)

    languages = {s.language for s in segments if s.language}
    language = next(iter(languages), None)

    speakers = {s.speaker_label for s in segments if s.speaker_label}
    speaker_count = len(speakers)

    return TranscriptResponse(
        segments=items,
        total_duration=total_duration,
        language=language,
        speaker_count=speaker_count,
    )


@router.post(
    "/transcribe",
    status_code=status.HTTP_202_ACCEPTED,
)
async def start_transcription_endpoint(
    case_id: str,
    asset_id: str,
    token_payload: dict[str, Any] = Depends(  # noqa: B008
        require_authenticated
    ),
    session: AsyncIterator[AsyncSession] = Depends(  # noqa: B008
        get_db_session
    ),
) -> dict[str, Any]:
    """start transcription workflow (editor+).

    returns 202 with workflow_id.
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

    # start temporal workflow
    workflow_id = f"transcribe-{asset_id}"
    try:
        from temporalio.client import Client

        from loom.config import get_settings
        from loom.workflows.transcription_workflow import (
            TranscriptionWorkflow,
        )

        settings = get_settings()
        client = await Client.connect(settings.temporal_host)
        await client.start_workflow(
            TranscriptionWorkflow.run,
            asset_id,
            id=workflow_id,
            task_queue="loom-ingest",
        )
    except Exception:
        # temporal unavailable; return the id so callers can
        # poll later
        logger.error(
            "failed to start transcription workflow for asset %s",
            asset_id,
            exc_info=True,
        )

    return {
        "workflow_id": workflow_id,
        "asset_id": asset_id,
        "status": "accepted",
    }
