from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


class ExportCreate(BaseModel):
    name: str = Field(min_length=1)
    format: str = Field(
        pattern=r"^(zip|pdf_report|json_manifest|court_bundle|portable_bundle)$"
    )
    include_originals: bool = False
    # work-product firewall: whether the analysis layer (timeline
    # events, annotations, notes) ships in the bundle. None resolves
    # to a per-format default at creation: court bundles are
    # evidence-only productions unless counsel opts in; other formats
    # keep their historical full contents.
    include_analysis: bool | None = None
    event_ids: list[str] | None = None
    asset_ids: list[str] | None = None
    date_range_start: datetime | None = None
    date_range_end: datetime | None = None
    # pdf-report composition controls (the report builder ui); None
    # means "builder default" and is excluded from stored options so
    # it never clobbers the service-side defaults
    include_evidence: bool | None = None
    include_contradictions: bool | None = None
    include_custody: bool | None = None
    executive_summary: str | None = None


class ExportResponse(BaseModel):
    id: UUID
    case_id: UUID
    name: str
    format: str
    storage_key: str | None
    sha256_hash: str | None
    # populated by the detail endpoint once the bundle is complete;
    # list responses never presign
    download_url: str | None = None
    status: str
    manifest: Any | None = None
    # the export request as submitted, so the ui can show what a
    # completed bundle was asked to contain
    options: Any | None = None
    created_by: UUID
    created_at: datetime

    model_config = {"from_attributes": True}


class ExportListResponse(BaseModel):
    items: list[ExportResponse]
    total: int
