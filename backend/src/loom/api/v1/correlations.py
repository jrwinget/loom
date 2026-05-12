from collections.abc import AsyncIterator
from typing import Any, Literal
from uuid import UUID

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Query,
    Request,
    status,
)
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from loom.dependencies import get_db_session
from loom.models.asset import Asset
from loom.models.correlation import (
    CorrelationCandidate,
    CorrelationCandidateMember,
)
from loom.schemas.correlation import (
    CorrelationCandidateDecisionRequest,
    CorrelationCandidateListResponse,
    CorrelationCandidateMemberResponse,
    CorrelationCandidateResponse,
)
from loom.security.rbac import (
    get_current_user_id,
    require_authenticated,
)
from loom.services.case import check_case_access
from loom.services.correlation import (
    compute_correlation_candidates,
    decide_candidate,
    persist_correlation_candidates,
)

router = APIRouter(
    prefix="/cases/{case_id}/correlations",
    tags=["correlations"],
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


async def _build_candidate_response(
    db: AsyncSession,
    candidate: CorrelationCandidate,
) -> CorrelationCandidateResponse:
    """load members with asset metadata and build response."""
    members_result = await db.execute(
        select(
            CorrelationCandidateMember,
            Asset.original_filename,
            Asset.capture_time,
        )
        .join(
            Asset,
            Asset.id == CorrelationCandidateMember.asset_id,
        )
        .where(CorrelationCandidateMember.candidate_id == candidate.id)
    )
    member_rows = members_result.all()
    members = [
        CorrelationCandidateMemberResponse(
            id=m.id,
            asset_id=m.asset_id,
            original_filename=fname,
            capture_time=ctime,
        )
        for m, fname, ctime in member_rows
    ]
    return CorrelationCandidateResponse(
        id=candidate.id,
        case_id=candidate.case_id,
        start_utc=candidate.start_utc,
        end_utc=candidate.end_utc,
        confidence=candidate.confidence,
        reasoning=candidate.reasoning,
        status=candidate.status,
        decided_by=candidate.decided_by,
        decided_at=candidate.decided_at,
        members=members,
        created_at=candidate.created_at,
    )


@router.get("", response_model=CorrelationCandidateListResponse)
async def list_correlation_candidates(
    case_id: str,
    candidate_status: Literal["pending", "accepted", "rejected"] | None = Query(
        None, alias="status"
    ),
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    token_payload: dict[str, Any] = Depends(  # noqa: B008
        require_authenticated
    ),
    session: AsyncIterator[AsyncSession] = Depends(  # noqa: B008
        get_db_session
    ),
) -> CorrelationCandidateListResponse:
    """list correlation candidates for a case."""
    db: AsyncSession = session  # type: ignore[assignment]
    user_id = get_current_user_id(token_payload)
    await _check_access(db, case_id, user_id)

    # count query
    count_q = select(func.count(CorrelationCandidate.id)).where(
        CorrelationCandidate.case_id == UUID(case_id)
    )
    if candidate_status:
        count_q = count_q.where(CorrelationCandidate.status == candidate_status)
    total_result = await db.execute(count_q)
    total = total_result.scalar_one()

    # paginated candidates
    query = (
        select(CorrelationCandidate)
        .where(CorrelationCandidate.case_id == UUID(case_id))
        .offset(skip)
        .limit(limit)
        .order_by(CorrelationCandidate.created_at.desc())
    )
    if candidate_status:
        query = query.where(CorrelationCandidate.status == candidate_status)
    result = await db.execute(query)
    candidates = list(result.scalars().all())

    candidate_responses = [
        await _build_candidate_response(db, c) for c in candidates
    ]

    return CorrelationCandidateListResponse(
        candidates=candidate_responses,
        total=total,
    )


@router.post(
    "/scan",
    response_model=CorrelationCandidateListResponse,
    status_code=status.HTTP_200_OK,
)
async def scan_correlation_candidates(
    case_id: str,
    token_payload: dict[str, Any] = Depends(  # noqa: B008
        require_authenticated
    ),
    session: AsyncIterator[AsyncSession] = Depends(  # noqa: B008
        get_db_session
    ),
) -> CorrelationCandidateListResponse:
    """compute and persist correlation candidates for a case."""
    db: AsyncSession = session  # type: ignore[assignment]
    user_id = get_current_user_id(token_payload)
    await _check_access(db, case_id, user_id, "editor")

    try:
        computed = await compute_correlation_candidates(db, case_id)
    except ValueError as exc:
        # service raises ValueError when a case exceeds the
        # MAX_ASSETS_PER_SCAN cap; surface as 422 so clients can
        # split or skip rather than hammer the endpoint.
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc
    persisted = await persist_correlation_candidates(db, case_id, computed)
    await db.commit()

    candidate_responses = [
        await _build_candidate_response(db, c) for c in persisted
    ]

    return CorrelationCandidateListResponse(
        candidates=candidate_responses,
        total=len(candidate_responses),
    )


@router.post(
    "/{candidate_id}/decide",
    response_model=CorrelationCandidateResponse,
)
async def decide_correlation_candidate(
    case_id: str,
    candidate_id: str,
    body: CorrelationCandidateDecisionRequest,
    request: Request,
    token_payload: dict[str, Any] = Depends(  # noqa: B008
        require_authenticated
    ),
    session: AsyncIterator[AsyncSession] = Depends(  # noqa: B008
        get_db_session
    ),
) -> CorrelationCandidateResponse:
    """accept or reject a correlation candidate."""
    db: AsyncSession = session  # type: ignore[assignment]
    user_id = get_current_user_id(token_payload)
    await _check_access(db, case_id, user_id, "editor")

    # verify candidate belongs to case
    result = await db.execute(
        select(CorrelationCandidate).where(
            CorrelationCandidate.id == UUID(candidate_id),
            CorrelationCandidate.case_id == UUID(case_id),
        )
    )
    candidate = result.scalar_one_or_none()
    if not candidate:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="correlation candidate not found",
        )

    ip_address = request.client.host if request.client else None
    try:
        updated = await decide_candidate(
            db,
            candidate_id,
            user_id,
            body.status,
            ip_address=ip_address,
        )
    except ValueError as exc:
        # service raises ValueError for already-decided candidates;
        # surface as 409 so clients can distinguish from 404.
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc
    await db.commit()
    await db.refresh(updated)

    return await _build_candidate_response(db, updated)
