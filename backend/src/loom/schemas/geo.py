from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class GeoAssetResponse(BaseModel):
    id: UUID
    original_filename: str
    media_type: str
    lat: float
    lon: float
    capture_time: datetime | None

    model_config = {"from_attributes": True}


class GeoEventResponse(BaseModel):
    id: UUID
    title: str
    status: str
    lat: float
    lon: float
    event_time_start: datetime
    has_contradictions: bool = False

    model_config = {"from_attributes": True}


class GeoBoundsResponse(BaseModel):
    min_lat: float
    max_lat: float
    min_lon: float
    max_lon: float
    time_start: datetime | None
    time_end: datetime | None
