from collections.abc import AsyncIterator
from typing import Any

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    status,
)
from minio import Minio
from sqlalchemy.ext.asyncio import AsyncSession

from loom.dependencies import get_db_session, get_minio_client
from loom.schemas.provenance import (
    ProvenanceListResponse,
    ProvenanceRecordResponse,
)
from loom.security.rbac import (
    get_current_user_id,
    require_authenticated,
)
from loom.services.case import check_case_access
from loom.services.provenance import (
    embed_provenance_in_export,
    get_asset_provenance,
    get_export_provenance,
)
from loom.services.storage import StorageService

router = APIRouter(
    prefix="/cases/{case_id}",
    tags=["provenance"],
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


@router.get(
    "/assets/{asset_id}/provenance",
    response_model=ProvenanceListResponse,
)
async def get_asset_provenance_endpoint(
    case_id: str,
    asset_id: str,
    token_payload: dict[str, Any] = Depends(  # noqa: B008
        require_authenticated
    ),
    session: AsyncIterator[AsyncSession] = Depends(  # noqa: B008
        get_db_session
    ),
) -> ProvenanceListResponse:
    """list provenance records for an asset (viewer+)."""
    db: AsyncSession = session  # type: ignore[assignment]
    user_id = get_current_user_id(token_payload)
    await _check_access(db, case_id, user_id)

    records = await get_asset_provenance(db, asset_id, case_id)
    items = [ProvenanceRecordResponse.model_validate(r) for r in records]
    return ProvenanceListResponse(items=items, total=len(items))


@router.get(
    "/exports/{export_id}/provenance",
    response_model=ProvenanceListResponse,
)
async def get_export_provenance_endpoint(
    case_id: str,
    export_id: str,
    token_payload: dict[str, Any] = Depends(  # noqa: B008
        require_authenticated
    ),
    session: AsyncIterator[AsyncSession] = Depends(  # noqa: B008
        get_db_session
    ),
) -> ProvenanceListResponse:
    """list provenance records for an export (viewer+)."""
    db: AsyncSession = session  # type: ignore[assignment]
    user_id = get_current_user_id(token_payload)
    await _check_access(db, case_id, user_id)

    records = await get_export_provenance(db, export_id, case_id)
    items = [ProvenanceRecordResponse.model_validate(r) for r in records]
    return ProvenanceListResponse(items=items, total=len(items))


@router.post(
    "/exports/{export_id}/provenance/embed",
    status_code=status.HTTP_202_ACCEPTED,
)
async def embed_provenance_endpoint(
    case_id: str,
    export_id: str,
    token_payload: dict[str, Any] = Depends(  # noqa: B008
        require_authenticated
    ),
    session: AsyncIterator[AsyncSession] = Depends(  # noqa: B008
        get_db_session
    ),
    minio_client: Minio = Depends(  # noqa: B008
        get_minio_client
    ),
) -> dict[str, str]:
    """trigger c2pa provenance embedding for an export.

    returns 202 if c2pa is available and embedding started,
    501 if c2pa-python is not installed.
    """
    db: AsyncSession = session  # type: ignore[assignment]
    user_id = get_current_user_id(token_payload)
    await _check_access(db, case_id, user_id, "editor")

    # check c2pa availability before starting work
    from loom.services.provenance import _c2pa_available

    if not _c2pa_available():
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail="c2pa-python is not installed; "
            "provenance embedding unavailable",
        )

    storage = StorageService(minio_client)

    result = await embed_provenance_in_export(db, export_id, case_id, storage)

    return {
        "status": "accepted",
        "embedded": str(result),
    }
