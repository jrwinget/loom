from typing import Any

from pydantic import BaseModel, Field


class SearchResult(BaseModel):
    type: str
    id: str
    text: str
    asset_id: str | None = None
    relevance_score: float = 0.0
    metadata: dict[str, Any] = Field(default_factory=dict)


class SearchResponse(BaseModel):
    results: list[SearchResult]
    total: int
    facets: dict[str, int]


class SearchQuery(BaseModel):
    q: str = Field(min_length=1)
    types: list[str] | None = None
    skip: int = Field(default=0, ge=0)
    limit: int = Field(default=50, ge=1, le=200)
