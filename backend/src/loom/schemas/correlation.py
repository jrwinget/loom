from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field


class CorrelationCandidateMemberResponse(BaseModel):
    id: UUID
    asset_id: UUID
    original_filename: str | None = None
    capture_time: datetime | None = None

    model_config = {"from_attributes": True}


class CorrelationCandidateResponse(BaseModel):
    id: UUID
    case_id: UUID
    start_utc: datetime
    end_utc: datetime
    confidence: float = Field(ge=0.0, le=1.0)
    reasoning: dict[str, Any]
    status: Literal["pending", "accepted", "rejected"]
    decided_by: UUID | None = None
    decided_at: datetime | None = None
    members: list[CorrelationCandidateMemberResponse]
    created_at: datetime

    model_config = {"from_attributes": True}


class CorrelationCandidateListResponse(BaseModel):
    candidates: list[CorrelationCandidateResponse]
    total: int


class CorrelationCandidateDecisionRequest(BaseModel):
    """accept or reject a candidate. no merge happens here."""

    status: Literal["accepted", "rejected"]
