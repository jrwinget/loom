from collections.abc import AsyncIterator
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from loom.dependencies import get_db_session
from loom.schemas.redaction import (
    RedactionCreate,
    RedactionListResponse,
    RedactionResponse,
)
from loom.security.rbac import (
    get_current_user_id,
    require_authenticated,
)
from loom.services.case import check_case_access
from loom.services.redaction import (
    apply_redaction,
    create_redaction,
    get_redaction,
    get_redactions,
)

router = APIRouter(
    prefix="/cases/{case_id}/assets/{asset_id}/redactions",
    tags=["redactions"],
)


@router.post(
    "",
    response_model=RedactionResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_asset_redaction(
    case_id: str,
    asset_id: str,
    body: RedactionCreate,
    token_payload: dict[str, Any] = Depends(  # noqa: B008
        require_authenticated
    ),
    session: AsyncIterator[AsyncSession] = Depends(  # noqa: B008
        get_db_session
    ),
) -> RedactionResponse:
    """create a redaction for an asset (editor+)."""
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

    regions = [r.model_dump() for r in body.regions]
    redaction = await create_redaction(
        db,
        asset_id,
        user_id,
        body.redaction_type,
        regions,
    )
    await db.commit()
    await db.refresh(redaction)

    return RedactionResponse.model_validate(redaction)


@router.get("", response_model=RedactionListResponse)
async def list_asset_redactions(
    case_id: str,
    asset_id: str,
    skip: int = 0,
    limit: int = 20,
    token_payload: dict[str, Any] = Depends(  # noqa: B008
        require_authenticated
    ),
    session: AsyncIterator[AsyncSession] = Depends(  # noqa: B008
        get_db_session
    ),
) -> RedactionListResponse:
    """list redactions for an asset (viewer+)."""
    db: AsyncSession = session  # type: ignore[assignment]
    user_id = get_current_user_id(token_payload)

    has_access = await check_case_access(db, case_id, user_id)
    if not has_access:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="insufficient case access",
        )

    items, total = await get_redactions(db, asset_id, skip, limit)
    return RedactionListResponse(
        items=[RedactionResponse.model_validate(r) for r in items],
        total=total,
        skip=skip,
        limit=limit,
    )


@router.get(
    "/{redaction_id}",
    response_model=RedactionResponse,
)
async def get_single_redaction(
    case_id: str,
    asset_id: str,
    redaction_id: str,
    token_payload: dict[str, Any] = Depends(  # noqa: B008
        require_authenticated
    ),
    session: AsyncIterator[AsyncSession] = Depends(  # noqa: B008
        get_db_session
    ),
) -> RedactionResponse:
    """get a single redaction by id (viewer+)."""
    db: AsyncSession = session  # type: ignore[assignment]
    user_id = get_current_user_id(token_payload)

    has_access = await check_case_access(db, case_id, user_id)
    if not has_access:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="insufficient case access",
        )

    redaction = await get_redaction(db, redaction_id)
    if not redaction:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="redaction not found",
        )

    return RedactionResponse.model_validate(redaction)


@router.post(
    "/{redaction_id}/apply",
    response_model=RedactionResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def apply_asset_redaction(
    case_id: str,
    asset_id: str,
    redaction_id: str,
    token_payload: dict[str, Any] = Depends(  # noqa: B008
        require_authenticated
    ),
    session: AsyncIterator[AsyncSession] = Depends(  # noqa: B008
        get_db_session
    ),
) -> RedactionResponse:
    """trigger redaction processing (editor+)."""
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

    redaction = await get_redaction(db, redaction_id)
    if not redaction:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="redaction not found",
        )

    # TODO: fetch image bytes from minio for image redactions
    # for now, mark as complete via stub
    updated = await apply_redaction(db, redaction)
    await db.commit()
    await db.refresh(updated)

    return RedactionResponse.model_validate(updated)
