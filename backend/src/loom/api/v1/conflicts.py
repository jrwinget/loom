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
from loom.schemas.conflict import (
    ConflictDetailResponse,
    ConflictListResponse,
    ConflictResolutionCreate,
    ConflictResolutionResponse,
    ConflictResolutionUpdate,
)
from loom.security.rbac import (
    get_current_user_id,
    require_authenticated,
)
from loom.services.case import check_case_access
from loom.services.conflict import (
    create_resolution,
    get_event_conflicts,
    list_case_conflicts,
    update_resolution,
)

router = APIRouter(
    prefix="/cases/{case_id}",
    tags=["conflicts"],
)


@router.get(
    "/conflicts",
    response_model=ConflictListResponse,
)
async def list_conflicts_endpoint(
    case_id: str,
    resolved: bool | None = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    token_payload: dict[str, Any] = Depends(  # noqa: B008
        require_authenticated
    ),
    session: AsyncIterator[AsyncSession] = Depends(  # noqa: B008
        get_db_session
    ),
) -> ConflictListResponse:
    """list events with conflicts (viewer+)."""
    db: AsyncSession = session  # type: ignore[assignment]
    user_id = get_current_user_id(token_payload)

    has_access = await check_case_access(db, case_id, user_id)
    if not has_access:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="insufficient case access",
        )

    items, total = await list_case_conflicts(
        db,
        case_id,
        resolved=resolved,
        skip=skip,
        limit=limit,
    )
    return ConflictListResponse(items=items, total=total)


@router.get(
    "/events/{event_id}/conflicts",
    response_model=ConflictDetailResponse,
)
async def get_event_conflicts_endpoint(
    case_id: str,
    event_id: str,
    token_payload: dict[str, Any] = Depends(  # noqa: B008
        require_authenticated
    ),
    session: AsyncIterator[AsyncSession] = Depends(  # noqa: B008
        get_db_session
    ),
) -> ConflictDetailResponse:
    """conflict detail for an event (viewer+)."""
    db: AsyncSession = session  # type: ignore[assignment]
    user_id = get_current_user_id(token_payload)

    has_access = await check_case_access(db, case_id, user_id)
    if not has_access:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="insufficient case access",
        )

    detail = await get_event_conflicts(db, event_id, case_id)
    if detail is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="event not found in case",
        )

    return ConflictDetailResponse(**detail)


@router.post(
    "/events/{event_id}/conflicts/resolve",
    response_model=ConflictResolutionResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_resolution_endpoint(
    case_id: str,
    event_id: str,
    body: ConflictResolutionCreate,
    token_payload: dict[str, Any] = Depends(  # noqa: B008
        require_authenticated
    ),
    session: AsyncIterator[AsyncSession] = Depends(  # noqa: B008
        get_db_session
    ),
) -> ConflictResolutionResponse:
    """create a conflict resolution (editor+)."""
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

    try:
        resolution = await create_resolution(
            db,
            event_id,
            case_id,
            body.model_dump(),
            user_id,
        )
    except ValueError as err:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="event not found in case",
        ) from err

    return ConflictResolutionResponse(
        id=resolution.id,
        event_id=resolution.event_id,
        resolution_type=resolution.resolution_type,
        notes=resolution.notes,
        resolved_by=resolution.resolved_by,
        created_at=resolution.created_at,
    )


@router.patch(
    "/conflicts/resolutions/{resolution_id}",
    response_model=ConflictResolutionResponse,
)
async def update_resolution_endpoint(
    case_id: str,
    resolution_id: str,
    body: ConflictResolutionUpdate,
    token_payload: dict[str, Any] = Depends(  # noqa: B008
        require_authenticated
    ),
    session: AsyncIterator[AsyncSession] = Depends(  # noqa: B008
        get_db_session
    ),
) -> ConflictResolutionResponse:
    """update a conflict resolution (editor+)."""
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

    data = body.model_dump(exclude_unset=True)
    resolution = await update_resolution(db, resolution_id, case_id, data)
    if resolution is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="resolution not found",
        )

    return ConflictResolutionResponse(
        id=resolution.id,
        event_id=resolution.event_id,
        resolution_type=resolution.resolution_type,
        notes=resolution.notes,
        resolved_by=resolution.resolved_by,
        created_at=resolution.created_at,
    )
