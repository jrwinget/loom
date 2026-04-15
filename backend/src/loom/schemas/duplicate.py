from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class ClusterMemberResponse(BaseModel):
    id: UUID
    asset_id: UUID
    original_filename: str | None = None
    phash: str | None = None
    distance: float | None = None
    is_primary: bool

    model_config = {"from_attributes": True}


class DuplicateClusterResponse(BaseModel):
    id: UUID
    case_id: UUID
    status: str
    members: list[ClusterMemberResponse]
    created_at: datetime

    model_config = {"from_attributes": True}


class DuplicateListResponse(BaseModel):
    clusters: list[DuplicateClusterResponse]
    total: int


class ClusterUpdateRequest(BaseModel):
    status: str | None = None
    primary_asset_id: UUID | None = None
