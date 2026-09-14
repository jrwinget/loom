from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel


class NarrativeGenerateRequest(BaseModel):
    """scope for a new draft: the whole case's audit log, or one
    asset's chain-of-custody history. exactly one of the two."""

    asset_id: str | None = None


class NarrativeDraftResponse(BaseModel):
    id: UUID
    case_id: UUID
    asset_id: UUID | None
    status: str
    text: str
    source_entry_ids: list[str]
    model_name: str
    model_version: str
    model_params: dict[str, Any] | None
    generated_by: UUID
    reviewed_by: UUID | None
    reviewed_at: datetime | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class NarrativeDraftListResponse(BaseModel):
    items: list[NarrativeDraftResponse]
