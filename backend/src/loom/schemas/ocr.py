from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel


class OcrRegionResponse(BaseModel):
    id: UUID
    asset_id: UUID
    frame_number: int | None
    timestamp: float | None
    bounding_box: dict[str, Any] | None
    text: str
    confidence: float | None
    language: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


class OcrResultResponse(BaseModel):
    regions: list[OcrRegionResponse]
    total_regions: int
    languages_detected: list[str]
