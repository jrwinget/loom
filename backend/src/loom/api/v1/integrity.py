from collections.abc import AsyncIterator
from typing import Any

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Request,
    status,
)
from sqlalchemy.ext.asyncio import AsyncSession

from loom.dependencies import get_db_session, get_storage_backend
from loom.schemas.integrity import (
    CaseIntegrityResult,
    IntegrityReportResponse,
    IntegrityResult,
)
from loom.security.rbac import (
    get_current_user_id,
    require_authenticated,
)
from loom.services.case import check_case_access
from loom.services.integrity import (
    IntegrityError,
    generate_integrity_report,
    verify_asset_integrity,
    verify_case_integrity,
)
from loom.services.storage_backends import StorageBackend

router = APIRouter(
    prefix="/cases/{case_id}",
    tags=["integrity"],
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
    "/assets/{asset_id}/verify",
    response_model=IntegrityResult,
)
async def verify_single_asset(
    case_id: str,
    asset_id: str,
    request: Request,
    token_payload: dict[str, Any] = Depends(  # noqa: B008
        require_authenticated
    ),
    session: AsyncIterator[AsyncSession] = Depends(  # noqa: B008
        get_db_session
    ),
    storage: StorageBackend = Depends(  # noqa: B008
        get_storage_backend
    ),
) -> IntegrityResult:
    """verify integrity of a single asset's stored file."""
    db: AsyncSession = session  # type: ignore[assignment]
    user_id = get_current_user_id(token_payload)
    await _check_access(db, case_id, user_id, "editor")

    ip_address = request.client.host if request.client else None

    try:
        result = await verify_asset_integrity(
            db, storage, asset_id, user_id, ip_address
        )
    except IntegrityError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc

    await db.commit()
    return result


@router.post(
    "/verify",
    response_model=CaseIntegrityResult,
)
async def verify_case_assets(
    case_id: str,
    request: Request,
    token_payload: dict[str, Any] = Depends(  # noqa: B008
        require_authenticated
    ),
    session: AsyncIterator[AsyncSession] = Depends(  # noqa: B008
        get_db_session
    ),
    storage: StorageBackend = Depends(  # noqa: B008
        get_storage_backend
    ),
) -> CaseIntegrityResult:
    """verify integrity of all assets in a case."""
    db: AsyncSession = session  # type: ignore[assignment]
    user_id = get_current_user_id(token_payload)
    await _check_access(db, case_id, user_id, "editor")

    ip_address = request.client.host if request.client else None

    result = await verify_case_integrity(
        db, storage, case_id, user_id, ip_address
    )
    await db.commit()
    return result


@router.get(
    "/assets/{asset_id}/integrity-report",
    response_model=IntegrityReportResponse,
)
async def get_integrity_report(
    case_id: str,
    asset_id: str,
    request: Request,
    token_payload: dict[str, Any] = Depends(  # noqa: B008
        require_authenticated
    ),
    session: AsyncIterator[AsyncSession] = Depends(  # noqa: B008
        get_db_session
    ),
    storage: StorageBackend = Depends(  # noqa: B008
        get_storage_backend
    ),
) -> IntegrityReportResponse:
    """generate a court-ready integrity report for an asset."""
    db: AsyncSession = session  # type: ignore[assignment]
    user_id = get_current_user_id(token_payload)
    await _check_access(db, case_id, user_id, "viewer")

    ip_address = request.client.host if request.client else None

    try:
        report = await generate_integrity_report(
            db, storage, asset_id, user_id, ip_address
        )
    except IntegrityError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc

    await db.commit()
    return report
