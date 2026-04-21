from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, field_validator

RESOLUTION_TYPES = (
    "accepted_supporting",
    "accepted_contradicting",
    "noted",
    "dismissed",
)


class ConflictResolutionCreate(BaseModel):
    resolution_type: str
    notes: str | None = None

    @field_validator("resolution_type")
    @classmethod
    def validate_resolution_type(cls, v: str) -> str:
        if v not in RESOLUTION_TYPES:
            raise ValueError(
                f"resolution_type must be one of: {', '.join(RESOLUTION_TYPES)}"
            )
        return v


class ConflictResolutionUpdate(BaseModel):
    resolution_type: str | None = None
    notes: str | None = None

    @field_validator("resolution_type")
    @classmethod
    def validate_resolution_type(cls, v: str | None) -> str | None:
        if v is not None and v not in RESOLUTION_TYPES:
            raise ValueError(
                f"resolution_type must be one of: {', '.join(RESOLUTION_TYPES)}"
            )
        return v


class ConflictResolutionResponse(BaseModel):
    id: UUID
    event_id: UUID
    resolution_type: str
    notes: str | None
    resolved_by: UUID
    created_at: datetime

    model_config = {"from_attributes": True}


class EvidenceDetail(BaseModel):
    id: UUID
    asset_id: UUID | None
    original_filename: str | None = None
    annotation_id: UUID | None = None
    clip_start: float | None = None
    clip_end: float | None = None
    relationship: str
    notes: str | None = None

    model_config = {"from_attributes": True}


class ConflictDetailResponse(BaseModel):
    event_id: UUID
    event_title: str
    supporting: list[EvidenceDetail]
    contradicting: list[EvidenceDetail]
    resolutions: list[ConflictResolutionResponse]


class ConflictListItem(BaseModel):
    event_id: UUID
    event_title: str
    supporting_count: int
    contradicting_count: int
    resolution_count: int
    is_resolved: bool


class ConflictListResponse(BaseModel):
    items: list[ConflictListItem]
    total: int
