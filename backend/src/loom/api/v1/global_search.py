"""global (cross-case) search for the command palette.

distinct from the per-case search router: this resolves the caller's
case memberships and searches only within them, so it needs no
case_id in the path.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from loom.dependencies import get_db_session
from loom.security.rbac import get_current_user_id, require_authenticated
from loom.services.global_search import search_global

router = APIRouter(prefix="/search", tags=["search"])


class GlobalSearchResult(BaseModel):
    type: str
    id: str
    case_id: str
    title: str
    snippet: str | None = None


class GlobalSearchResponse(BaseModel):
    results: list[GlobalSearchResult]


@router.get("", response_model=GlobalSearchResponse)
async def global_search_endpoint(
    q: str = Query(..., min_length=1),
    limit: int = Query(20, ge=1, le=50),
    token_payload: dict[str, Any] = Depends(  # noqa: B008
        require_authenticated
    ),
    session: AsyncIterator[AsyncSession] = Depends(  # noqa: B008
        get_db_session
    ),
) -> GlobalSearchResponse:
    """search across the caller's accessible cases for the palette."""
    db: AsyncSession = session  # type: ignore[assignment]
    user_id = get_current_user_id(token_payload)
    rows = await search_global(db, user_id, q, limit=limit)
    return GlobalSearchResponse(
        results=[GlobalSearchResult(**row) for row in rows]
    )
