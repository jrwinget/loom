from collections.abc import AsyncIterator
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from loom.dependencies import get_db_session
from loom.schemas.search import SearchResponse, SearchResult
from loom.security.rbac import get_current_user_id, require_authenticated
from loom.services.case import check_case_access
from loom.services.search import search_case

router = APIRouter(
    prefix="/cases/{case_id}/search",
    tags=["search"],
)


@router.get("", response_model=SearchResponse)
async def search_endpoint(
    case_id: str,
    q: str = Query(..., min_length=1),
    types: str | None = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    token_payload: dict[str, Any] = Depends(  # noqa: B008
        require_authenticated
    ),
    session: AsyncIterator[AsyncSession] = Depends(  # noqa: B008
        get_db_session
    ),
) -> SearchResponse:
    """search across all content types in a case."""
    db: AsyncSession = session  # type: ignore[assignment]
    user_id = get_current_user_id(token_payload)

    has_access = await check_case_access(db, case_id, user_id)
    if not has_access:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="insufficient case access",
        )

    # parse comma-separated types
    result_types: list[str] | None = None
    if types:
        result_types = [t.strip() for t in types.split(",")]

    data = await search_case(db, case_id, q, result_types, skip, limit)

    results = [SearchResult(**r) for r in data["results"]]
    return SearchResponse(
        results=results,
        total=data["total"],
        facets=data["facets"],
    )
