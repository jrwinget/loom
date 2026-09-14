"""ai-drafted custody/audit narratives, gated behind human review.

generating and reviewing both require case editor+ access — a
read-only viewer must not be able to trigger egress of case metadata to
a configured text-generation endpoint. settings for the underlying
text-generation capability are configured separately (admin-only) under
``/settings/ai/text-generation``.
"""

from collections.abc import AsyncIterator
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from loom.dependencies import get_db_session
from loom.schemas.narrative import (
    NarrativeDraftListResponse,
    NarrativeDraftResponse,
    NarrativeGenerateRequest,
)
from loom.security.rbac import get_current_user_id, require_authenticated
from loom.services.case import check_case_access
from loom.services.narrative_generation import (
    NarrativeGenerationError,
    approve_narrative,
    generate_narrative,
    get_narrative,
    list_narratives,
    reject_narrative,
)

router = APIRouter(
    prefix="/cases/{case_id}/narratives",
    tags=["narratives"],
)


async def _require_access(
    db: AsyncSession, case_id: str, user_id: str, required_role: str
) -> None:
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
    response_model=NarrativeDraftResponse,
    status_code=status.HTTP_201_CREATED,
)
async def generate_narrative_endpoint(
    case_id: str,
    body: NarrativeGenerateRequest,
    token_payload: dict[str, Any] = Depends(  # noqa: B008
        require_authenticated
    ),
    session: AsyncIterator[AsyncSession] = Depends(  # noqa: B008
        get_db_session
    ),
) -> NarrativeDraftResponse:
    """draft a narrative over the case's audit log, or one asset's
    chain of custody when ``asset_id`` is given (requires editor+)."""
    db: AsyncSession = session  # type: ignore[assignment]
    user_id = get_current_user_id(token_payload)
    await _require_access(db, case_id, user_id, "editor")

    try:
        draft = await generate_narrative(
            db, case_id=case_id, asset_id=body.asset_id, user_id=user_id
        )
    except NarrativeGenerationError as err:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(err),
        ) from err
    return NarrativeDraftResponse.model_validate(draft)


@router.get("", response_model=NarrativeDraftListResponse)
async def list_narratives_endpoint(
    case_id: str,
    asset_id: str | None = Query(None),
    token_payload: dict[str, Any] = Depends(  # noqa: B008
        require_authenticated
    ),
    session: AsyncIterator[AsyncSession] = Depends(  # noqa: B008
        get_db_session
    ),
) -> NarrativeDraftListResponse:
    """list narrative drafts for a case, optionally scoped to an asset."""
    db: AsyncSession = session  # type: ignore[assignment]
    user_id = get_current_user_id(token_payload)
    await _require_access(db, case_id, user_id, "viewer")

    items = await list_narratives(db, case_id, asset_id=asset_id)
    return NarrativeDraftListResponse(
        items=[NarrativeDraftResponse.model_validate(i) for i in items]
    )


async def _get_owned_narrative(
    db: AsyncSession, case_id: str, narrative_id: str
) -> Any:
    narrative = await get_narrative(db, narrative_id)
    if narrative is None or str(narrative.case_id) != case_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="narrative not found",
        )
    return narrative


@router.get("/{narrative_id}", response_model=NarrativeDraftResponse)
async def get_narrative_endpoint(
    case_id: str,
    narrative_id: str,
    token_payload: dict[str, Any] = Depends(  # noqa: B008
        require_authenticated
    ),
    session: AsyncIterator[AsyncSession] = Depends(  # noqa: B008
        get_db_session
    ),
) -> NarrativeDraftResponse:
    db: AsyncSession = session  # type: ignore[assignment]
    user_id = get_current_user_id(token_payload)
    await _require_access(db, case_id, user_id, "viewer")

    narrative = await _get_owned_narrative(db, case_id, narrative_id)
    return NarrativeDraftResponse.model_validate(narrative)


@router.post("/{narrative_id}/approve", response_model=NarrativeDraftResponse)
async def approve_narrative_endpoint(
    case_id: str,
    narrative_id: str,
    token_payload: dict[str, Any] = Depends(  # noqa: B008
        require_authenticated
    ),
    session: AsyncIterator[AsyncSession] = Depends(  # noqa: B008
        get_db_session
    ),
) -> NarrativeDraftResponse:
    """mark a draft reviewed and approved — only approved drafts are
    ever eligible for export-bundle inclusion (requires editor+)."""
    db: AsyncSession = session  # type: ignore[assignment]
    user_id = get_current_user_id(token_payload)
    await _require_access(db, case_id, user_id, "editor")

    narrative = await _get_owned_narrative(db, case_id, narrative_id)
    updated = await approve_narrative(db, narrative, user_id=user_id)
    return NarrativeDraftResponse.model_validate(updated)


@router.post("/{narrative_id}/reject", response_model=NarrativeDraftResponse)
async def reject_narrative_endpoint(
    case_id: str,
    narrative_id: str,
    token_payload: dict[str, Any] = Depends(  # noqa: B008
        require_authenticated
    ),
    session: AsyncIterator[AsyncSession] = Depends(  # noqa: B008
        get_db_session
    ),
) -> NarrativeDraftResponse:
    """mark a draft reviewed and rejected (requires editor+)."""
    db: AsyncSession = session  # type: ignore[assignment]
    user_id = get_current_user_id(token_payload)
    await _require_access(db, case_id, user_id, "editor")

    narrative = await _get_owned_narrative(db, case_id, narrative_id)
    updated = await reject_narrative(db, narrative, user_id=user_id)
    return NarrativeDraftResponse.model_validate(updated)
