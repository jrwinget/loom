from collections.abc import AsyncIterator
from datetime import datetime
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
from loom.schemas.geo import (
    GeoAssetResponse,
    GeoBoundsResponse,
    GeoEventResponse,
)
from loom.security.rbac import (
    get_current_user_id,
    require_authenticated,
)
from loom.services.case import check_case_access
from loom.services.geo import (
    get_geo_bounds,
    get_geotagged_assets,
    get_geotagged_events,
)

router = APIRouter(
    prefix="/cases/{case_id}/geo",
    tags=["geo"],
)


async def _check_viewer_access(
    db: AsyncSession,
    case_id: str,
    user_id: str,
) -> None:
    """verify user has at least viewer access."""
    has_access = await check_case_access(
        db, case_id, user_id, required_role="viewer"
    )
    if not has_access:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="insufficient case access",
        )


@router.get(
    "/assets",
    response_model=list[GeoAssetResponse],
)
async def get_geo_assets_endpoint(
    case_id: str,
    time_start: datetime | None = Query(  # noqa: B008
        None
    ),
    time_end: datetime | None = Query(None),  # noqa: B008
    token_payload: dict[str, Any] = Depends(  # noqa: B008
        require_authenticated
    ),
    session: AsyncIterator[AsyncSession] = Depends(  # noqa: B008
        get_db_session
    ),
) -> list[GeoAssetResponse]:
    """get geotagged assets for map display (viewer+)."""
    db: AsyncSession = session  # type: ignore[assignment]
    user_id = get_current_user_id(token_payload)
    await _check_viewer_access(db, case_id, user_id)

    items = await get_geotagged_assets(db, case_id, time_start, time_end)
    return [GeoAssetResponse(**item) for item in items]


@router.get(
    "/events",
    response_model=list[GeoEventResponse],
)
async def get_geo_events_endpoint(
    case_id: str,
    time_start: datetime | None = Query(  # noqa: B008
        None
    ),
    time_end: datetime | None = Query(None),  # noqa: B008
    token_payload: dict[str, Any] = Depends(  # noqa: B008
        require_authenticated
    ),
    session: AsyncIterator[AsyncSession] = Depends(  # noqa: B008
        get_db_session
    ),
) -> list[GeoEventResponse]:
    """get geotagged events for map display (viewer+)."""
    db: AsyncSession = session  # type: ignore[assignment]
    user_id = get_current_user_id(token_payload)
    await _check_viewer_access(db, case_id, user_id)

    items = await get_geotagged_events(db, case_id, time_start, time_end)
    return [GeoEventResponse(**item) for item in items]


@router.get(
    "/bounds",
    response_model=GeoBoundsResponse | None,
)
async def get_geo_bounds_endpoint(
    case_id: str,
    token_payload: dict[str, Any] = Depends(  # noqa: B008
        require_authenticated
    ),
    session: AsyncIterator[AsyncSession] = Depends(  # noqa: B008
        get_db_session
    ),
) -> GeoBoundsResponse | None:
    """get bounding box for all geotagged items (viewer+)."""
    db: AsyncSession = session  # type: ignore[assignment]
    user_id = get_current_user_id(token_payload)
    await _check_viewer_access(db, case_id, user_id)

    bounds = await get_geo_bounds(db, case_id)
    if bounds is None:
        return None
    return GeoBoundsResponse(**bounds)
