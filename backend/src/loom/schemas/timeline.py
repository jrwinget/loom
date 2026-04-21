from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field, field_validator

EVENT_STATUSES = ("draft", "proposed", "accepted", "rejected")
TIME_PRECISIONS = ("exact", "approximate", "estimated")
LOCATION_CONFIDENCES = ("verified", "approximate", "unknown")
EVIDENCE_RELATIONSHIPS = ("supports", "contradicts", "context")


class TimelineEventCreate(BaseModel):
    title: str = Field(min_length=1)
    description: str | None = None
    event_time_start: datetime
    event_time_end: datetime | None = None
    time_precision: str = "approximate"
    location_description: str | None = None
    location_lat: float | None = None
    location_lon: float | None = None
    location_confidence: str = "unknown"
    status: str = "draft"

    @field_validator("status")
    @classmethod
    def validate_status(cls, v: str) -> str:
        if v not in EVENT_STATUSES:
            raise ValueError(
                f"status must be one of: {', '.join(EVENT_STATUSES)}"
            )
        return v

    @field_validator("time_precision")
    @classmethod
    def validate_time_precision(cls, v: str) -> str:
        if v not in TIME_PRECISIONS:
            raise ValueError(
                f"time_precision must be one of: {', '.join(TIME_PRECISIONS)}"
            )
        return v

    @field_validator("location_confidence")
    @classmethod
    def validate_location_confidence(cls, v: str) -> str:
        if v not in LOCATION_CONFIDENCES:
            raise ValueError(
                f"location_confidence must be one of: "
                f"{', '.join(LOCATION_CONFIDENCES)}"
            )
        return v


class TimelineEventUpdate(BaseModel):
    title: str | None = None
    description: str | None = None
    event_time_start: datetime | None = None
    event_time_end: datetime | None = None
    time_precision: str | None = None
    location_description: str | None = None
    location_lat: float | None = None
    location_lon: float | None = None
    location_confidence: str | None = None
    status: str | None = None

    @field_validator("status")
    @classmethod
    def validate_status(cls, v: str | None) -> str | None:
        if v is not None and v not in EVENT_STATUSES:
            raise ValueError(
                f"status must be one of: {', '.join(EVENT_STATUSES)}"
            )
        return v

    @field_validator("time_precision")
    @classmethod
    def validate_time_precision(cls, v: str | None) -> str | None:
        if v is not None and v not in TIME_PRECISIONS:
            raise ValueError(
                f"time_precision must be one of: {', '.join(TIME_PRECISIONS)}"
            )
        return v

    @field_validator("location_confidence")
    @classmethod
    def validate_location_confidence(cls, v: str | None) -> str | None:
        if v is not None and v not in LOCATION_CONFIDENCES:
            raise ValueError(
                f"location_confidence must be one of: "
                f"{', '.join(LOCATION_CONFIDENCES)}"
            )
        return v


class EvidenceLinkCreate(BaseModel):
    asset_id: str | None = None
    annotation_id: str | None = None
    derivative_id: str | None = None
    clip_start: float | None = None
    clip_end: float | None = None
    relationship: str
    notes: str | None = None

    @field_validator("relationship")
    @classmethod
    def validate_relationship(cls, v: str) -> str:
        if v not in EVIDENCE_RELATIONSHIPS:
            raise ValueError(
                f"relationship must be one of: "
                f"{', '.join(EVIDENCE_RELATIONSHIPS)}"
            )
        return v


class EvidenceLinkResponse(BaseModel):
    id: UUID
    event_id: UUID
    asset_id: UUID | None
    annotation_id: UUID | None
    derivative_id: UUID | None
    clip_start: float | None
    clip_end: float | None
    relationship: str
    notes: str | None
    linked_by: UUID
    linked_at: datetime

    model_config = {"from_attributes": True}


class TimelineEventResponse(BaseModel):
    id: UUID
    case_id: UUID
    title: str
    description: str | None
    event_time_start: datetime
    event_time_end: datetime | None
    time_precision: str
    location_description: str | None
    location_lat: float | None
    location_lon: float | None
    location_confidence: str
    status: str
    created_by: UUID
    created_at: datetime
    updated_at: datetime
    evidence_count: int = 0
    has_contradictions: bool = False

    model_config = {"from_attributes": True}


class TimelineEventListResponse(BaseModel):
    items: list[TimelineEventResponse]
    total: int


class TimelineEventDetailResponse(BaseModel):
    id: UUID
    case_id: UUID
    title: str
    description: str | None
    event_time_start: datetime
    event_time_end: datetime | None
    time_precision: str
    location_description: str | None
    location_lat: float | None
    location_lon: float | None
    location_confidence: str
    status: str
    created_by: UUID
    created_at: datetime
    updated_at: datetime
    evidence_count: int = 0
    has_contradictions: bool = False
    evidence: list[EvidenceLinkResponse] = []

    model_config = {"from_attributes": True}


class TimelineResponse(BaseModel):
    events: list[TimelineEventDetailResponse]
