from uuid import UUID

from pydantic import BaseModel


class TranscriptSegmentResponse(BaseModel):
    """single transcript segment."""

    id: UUID
    asset_id: UUID
    speaker_label: str | None
    start_time: float
    end_time: float
    text: str
    confidence: float | None
    language: str | None

    model_config = {"from_attributes": True}


class TranscriptResponse(BaseModel):
    """full transcript for an asset."""

    segments: list[TranscriptSegmentResponse]
    total_duration: float
    language: str | None
    speaker_count: int
