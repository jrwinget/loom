from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field


class RedactionRegion(BaseModel):
    """a spatial or temporal region to redact."""

    type: Literal["rect", "circle", "temporal"] = Field(
        description="region shape: rect/circle for spatial, "
        "temporal for audio-only"
    )
    x: float | None = Field(
        default=None,
        description="left edge (fraction 0-1)",
    )
    y: float | None = Field(
        default=None,
        description="top edge (fraction 0-1)",
    )
    w: float | None = Field(
        default=None,
        description="width (fraction 0-1)",
    )
    h: float | None = Field(
        default=None,
        description="height (fraction 0-1)",
    )
    start_time: float | None = Field(
        default=None,
        description="start time in seconds",
    )
    end_time: float | None = Field(
        default=None,
        description="end time in seconds",
    )


class RedactionCreate(BaseModel):
    """request body for creating a redaction."""

    redaction_type: Literal["blur", "black_box", "pixelate", "audio_mute"]
    regions: list[RedactionRegion] = Field(
        min_length=1,
        description="at least one region to redact",
    )


class RedactionResponse(BaseModel):
    """response for a single redaction record."""

    id: UUID
    asset_id: UUID
    redacted_by: UUID
    redaction_type: str
    regions: list[RedactionRegion]
    status: str
    output_storage_key: str | None
    error_message: str | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class RedactionListResponse(BaseModel):
    """paginated list of redactions."""

    items: list[RedactionResponse]
    total: int
    skip: int
    limit: int
