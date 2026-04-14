from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field, field_validator

ANNOTATION_TYPES = (
    "observation",
    "claim",
    "dispute",
    "needs_verification",
    "note",
)


class AnnotationCreate(BaseModel):
    type: str
    content: str = Field(min_length=1)
    asset_id: str | None = None
    time_start: float | None = None
    time_end: float | None = None
    frame_number: int | None = None
    spatial_region: dict[str, Any] | None = None

    @field_validator("type")
    @classmethod
    def validate_type(cls, v: str) -> str:
        if v not in ANNOTATION_TYPES:
            raise ValueError(
                f"type must be one of: {', '.join(ANNOTATION_TYPES)}"
            )
        return v


class AnnotationUpdate(BaseModel):
    type: str | None = None
    content: str | None = None
    time_start: float | None = None
    time_end: float | None = None

    @field_validator("type")
    @classmethod
    def validate_type(cls, v: str | None) -> str | None:
        if v is not None and v not in ANNOTATION_TYPES:
            raise ValueError(
                f"type must be one of: {', '.join(ANNOTATION_TYPES)}"
            )
        return v


class AnnotationResponse(BaseModel):
    id: UUID
    case_id: UUID
    asset_id: UUID | None
    type: str
    content: str
    time_start: float | None
    time_end: float | None
    frame_number: int | None
    spatial_region: dict[str, Any] | None
    created_by: UUID
    created_by_email: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class AnnotationListResponse(BaseModel):
    items: list[AnnotationResponse]
    total: int
