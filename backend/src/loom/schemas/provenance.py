from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel


class ProvenanceRecordResponse(BaseModel):
    id: UUID
    asset_id: UUID | None = None
    export_id: UUID | None = None
    manifest_data: dict[str, Any]
    claim_generator: str
    actions: list[dict[str, Any]]
    created_at: datetime

    model_config = {"from_attributes": True}


class ProvenanceListResponse(BaseModel):
    items: list[ProvenanceRecordResponse]
    total: int


class ProvenanceEmbedRequest(BaseModel):
    export_id: str
