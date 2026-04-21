import logging
from collections.abc import AsyncIterator
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from loom.dependencies import get_db_session
from loom.schemas.organization import (
    SharedEvidenceCreate,
    SharedEvidenceResponse,
)
from loom.security.rbac import get_current_user_id, require_authenticated
from loom.services.case import check_case_access
from loom.services.shared_evidence import (
    list_shared_from_case,
    list_shared_with_case,
    revoke_share,
    share_evidence,
)

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/cases/{case_id}/shared-evidence",
    tags=["shared-evidence"],
)


@router.post(
    "",
    response_model=SharedEvidenceResponse,
    status_code=status.HTTP_201_CREATED,
)
async def share_evidence_endpoint(
    case_id: str,
    body: SharedEvidenceCreate,
    token_payload: dict[str, Any] = Depends(  # noqa: B008
        require_authenticated
    ),
    session: AsyncIterator[AsyncSession] = Depends(  # noqa: B008
        get_db_session
    ),
) -> SharedEvidenceResponse:
    """share evidence from this case to another."""
    db: AsyncSession = session  # type: ignore[assignment]
    user_id = get_current_user_id(token_payload)

    try:
        link = await share_evidence(
            db,
            source_case_id=case_id,
            target_case_id=body.target_case_id,
            asset_id=body.asset_id,
            user_id=user_id,
            access_level=body.access_level,
            expires_at=body.expires_at,
        )
    except PermissionError as err:
        logger.warning(
            "permission denied for shared evidence: %s",
            err,
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="insufficient permissions for this operation",
        ) from err
    except ValueError as err:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="asset not found in source case",
        ) from err

    return SharedEvidenceResponse(
        id=link.id,
        source_case_id=link.source_case_id,
        target_case_id=link.target_case_id,
        asset_id=link.asset_id,
        shared_by=link.shared_by,
        access_level=link.access_level,
        expires_at=link.expires_at,
        created_at=link.created_at,
    )


@router.get(
    "/incoming",
    response_model=list[SharedEvidenceResponse],
)
async def list_incoming_endpoint(
    case_id: str,
    token_payload: dict[str, Any] = Depends(  # noqa: B008
        require_authenticated
    ),
    session: AsyncIterator[AsyncSession] = Depends(  # noqa: B008
        get_db_session
    ),
) -> list[SharedEvidenceResponse]:
    """list evidence shared to this case."""
    db: AsyncSession = session  # type: ignore[assignment]
    user_id = get_current_user_id(token_payload)

    has_access = await check_case_access(db, case_id, user_id)
    if not has_access:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="insufficient case access",
        )

    links = await list_shared_with_case(db, case_id)
    return [
        SharedEvidenceResponse(
            id=ln.id,
            source_case_id=ln.source_case_id,
            target_case_id=ln.target_case_id,
            asset_id=ln.asset_id,
            original_filename=getattr(ln, "original_filename", None),
            shared_by=ln.shared_by,
            access_level=ln.access_level,
            expires_at=ln.expires_at,
            created_at=ln.created_at,
        )
        for ln in links
    ]


@router.get(
    "/outgoing",
    response_model=list[SharedEvidenceResponse],
)
async def list_outgoing_endpoint(
    case_id: str,
    token_payload: dict[str, Any] = Depends(  # noqa: B008
        require_authenticated
    ),
    session: AsyncIterator[AsyncSession] = Depends(  # noqa: B008
        get_db_session
    ),
) -> list[SharedEvidenceResponse]:
    """list evidence shared from this case."""
    db: AsyncSession = session  # type: ignore[assignment]
    user_id = get_current_user_id(token_payload)

    has_access = await check_case_access(db, case_id, user_id)
    if not has_access:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="insufficient case access",
        )

    links = await list_shared_from_case(db, case_id)
    return [
        SharedEvidenceResponse(
            id=ln.id,
            source_case_id=ln.source_case_id,
            target_case_id=ln.target_case_id,
            asset_id=ln.asset_id,
            original_filename=getattr(ln, "original_filename", None),
            shared_by=ln.shared_by,
            access_level=ln.access_level,
            expires_at=ln.expires_at,
            created_at=ln.created_at,
        )
        for ln in links
    ]


@router.delete(
    "/{link_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def revoke_share_endpoint(
    case_id: str,
    link_id: str,
    token_payload: dict[str, Any] = Depends(  # noqa: B008
        require_authenticated
    ),
    session: AsyncIterator[AsyncSession] = Depends(  # noqa: B008
        get_db_session
    ),
) -> None:
    """revoke a shared evidence link."""
    db: AsyncSession = session  # type: ignore[assignment]
    user_id = get_current_user_id(token_payload)

    try:
        revoked = await revoke_share(db, link_id, case_id, user_id)
    except PermissionError as err:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="insufficient access on source case",
        ) from err

    if not revoked:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="shared evidence link not found",
        )
