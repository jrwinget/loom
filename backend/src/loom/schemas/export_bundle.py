from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


class ExportCreate(BaseModel):
    name: str = Field(min_length=1)
    format: str = Field(pattern=r"^(zip|pdf_report|json_manifest)$")
    include_originals: bool = False
    event_ids: list[str] | None = None
    asset_ids: list[str] | None = None
    date_range_start: datetime | None = None
    date_range_end: datetime | None = None


class ExportResponse(BaseModel):
    id: UUID
    case_id: UUID
    name: str
    format: str
    storage_key: str | None
    sha256_hash: str | None
    status: str
    manifest: Any | None = None
    created_by: UUID
    created_at: datetime

    model_config = {"from_attributes": True}


class ExportListResponse(BaseModel):
    items: list[ExportResponse]
    total: int
