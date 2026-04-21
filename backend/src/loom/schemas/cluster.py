from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class ClusterItemResponse(BaseModel):
    id: UUID
    asset_id: UUID
    original_filename: str | None = None
    content_type: str
    content_id: UUID
    absolute_time_start: datetime
    absolute_time_end: datetime | None
    text_preview: str

    model_config = {"from_attributes": True}


class EventClusterResponse(BaseModel):
    id: UUID
    case_id: UUID
    status: str
    proposed_title: str
    proposed_description: str | None
    time_window_start: datetime
    time_window_end: datetime
    event_id: UUID | None
    items: list[ClusterItemResponse] = []
    created_at: datetime

    model_config = {"from_attributes": True}


class ClusterListResponse(BaseModel):
    items: list[EventClusterResponse]
    total: int


class ProposeClusterRequest(BaseModel):
    window_seconds: int = Field(default=60, ge=5, le=3600)


class AcceptClusterRequest(BaseModel):
    title: str = Field(min_length=1)
    description: str | None = None


class MergeClustersRequest(BaseModel):
    cluster_ids: list[str] = Field(min_length=2)


class SplitClusterRequest(BaseModel):
    item_ids: list[str] = Field(min_length=1)
