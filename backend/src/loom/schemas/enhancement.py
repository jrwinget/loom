"""request/response models for the clarity-assist enhancement api.

the parameter ranges mirror ``EnhancementParams.__post_init__`` in
the service so an invalid request is rejected with a 422 before any
work is dispatched.
"""

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field


class EnhancementParamsSchema(BaseModel):
    """deterministic ffmpeg filter parameters; defaults are neutral."""

    brightness: float = Field(0.0, ge=-1.0, le=1.0)
    contrast: float = Field(1.0, ge=0.0, le=4.0)
    saturation: float = Field(1.0, ge=0.0, le=3.0)
    gamma: float = Field(1.0, ge=0.1, le=10.0)
    denoise: int = Field(0, ge=0, le=10)
    sharpen: float = Field(0.0, ge=0.0, le=5.0)
    deinterlace: bool = False
    scale_factor: Literal[1, 2, 4] = 1


class EnhancementCreatedResponse(BaseModel):
    """202 body for a dispatched enhancement run."""

    workflow_id: str
    status: str
    params: EnhancementParamsSchema


class EnhancementSuggestResponse(BaseModel):
    """suggested starting parameters plus their human rationale."""

    params: EnhancementParamsSchema
    reasons: list[str]


class EnhancementDerivativeResponse(BaseModel):
    """one produced enhancement derivative with its provenance."""

    id: UUID
    generation_params: dict[str, Any] | None
    created_at: datetime
    download_url: str


class EnhancementListResponse(BaseModel):
    enhancements: list[EnhancementDerivativeResponse]
