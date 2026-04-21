"""chain of custody api endpoints."""

from collections.abc import AsyncIterator
from typing import Any
from uuid import UUID

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Query,
    status,
)
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from loom.dependencies import get_db_session
from loom.models.chain_of_custody import ChainOfCustodyEntry
from loom.schemas.custody import (
    CaseCustodyVerificationResult,
    CustodyEntryListResponse,
    CustodyEntryResponse,
    CustodyReportResponse,
    CustodyVerificationResult,
)
from loom.security.rbac import (
    get_current_user_id,
    require_authenticated,
)
from loom.services.case import check_case_access
from loom.services.custody_verification import (
    export_custody_report,
    verify_asset_chain,
    verify_case_custody,
)

router = APIRouter(tags=["custody"])


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


@router.get(
    "/cases/{case_id}/assets/{asset_id}/custody",
    response_model=CustodyEntryListResponse,
)
async def list_custody_entries(
    case_id: str,
    asset_id: str,
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    token_payload: dict[str, Any] = Depends(  # noqa: B008
        require_authenticated
    ),
    session: AsyncIterator[AsyncSession] = Depends(  # noqa: B008
        get_db_session
    ),
) -> CustodyEntryListResponse:
    """list custody entries for an asset."""
    db: AsyncSession = session  # type: ignore[assignment]
    user_id = get_current_user_id(token_payload)
    await _check_access(db, case_id, user_id)

    uid = UUID(asset_id)

    # total count
    count_q = select(func.count(ChainOfCustodyEntry.id)).where(
        ChainOfCustodyEntry.asset_id == uid
    )
    total_result = await db.execute(count_q)
    total = total_result.scalar_one()

    # paginated query
    query = (
        select(ChainOfCustodyEntry)
        .where(ChainOfCustodyEntry.asset_id == uid)
        .order_by(ChainOfCustodyEntry.timestamp.asc())
        .offset(skip)
        .limit(limit)
    )
    result = await db.execute(query)
    entries = list(result.scalars().all())

    return CustodyEntryListResponse(
        items=[CustodyEntryResponse.model_validate(e) for e in entries],
        total=total,
    )


@router.get(
    "/cases/{case_id}/assets/{asset_id}/custody/verify",
    response_model=CustodyVerificationResult,
)
async def verify_asset_custody(
    case_id: str,
    asset_id: str,
    token_payload: dict[str, Any] = Depends(  # noqa: B008
        require_authenticated
    ),
    session: AsyncIterator[AsyncSession] = Depends(  # noqa: B008
        get_db_session
    ),
) -> CustodyVerificationResult:
    """run verification on an asset's custody chain."""
    db: AsyncSession = session  # type: ignore[assignment]
    user_id = get_current_user_id(token_payload)
    await _check_access(db, case_id, user_id)

    return await verify_asset_chain(db, asset_id)


@router.get(
    "/cases/{case_id}/custody/verify",
    response_model=CaseCustodyVerificationResult,
)
async def verify_all_case_custody(
    case_id: str,
    token_payload: dict[str, Any] = Depends(  # noqa: B008
        require_authenticated
    ),
    session: AsyncIterator[AsyncSession] = Depends(  # noqa: B008
        get_db_session
    ),
) -> CaseCustodyVerificationResult:
    """verify custody chains for all assets in a case."""
    db: AsyncSession = session  # type: ignore[assignment]
    user_id = get_current_user_id(token_payload)
    await _check_access(db, case_id, user_id)

    return await verify_case_custody(db, case_id)


@router.get(
    "/cases/{case_id}/assets/{asset_id}/custody/report",
    response_model=CustodyReportResponse,
)
async def get_custody_report(
    case_id: str,
    asset_id: str,
    token_payload: dict[str, Any] = Depends(  # noqa: B008
        require_authenticated
    ),
    session: AsyncIterator[AsyncSession] = Depends(  # noqa: B008
        get_db_session
    ),
) -> CustodyReportResponse:
    """export a structured custody report for court submission."""
    db: AsyncSession = session  # type: ignore[assignment]
    user_id = get_current_user_id(token_payload)
    await _check_access(db, case_id, user_id)

    try:
        return await export_custody_report(db, asset_id)
    except ValueError as err:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(err),
        ) from err
