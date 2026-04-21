from typing import Any
from uuid import UUID

from pydantic import BaseModel


class SceneResponse(BaseModel):
    id: UUID
    asset_id: UUID
    scene_number: int
    start_time: float
    end_time: float
    start_frame: int
    end_frame: int
    thumbnail_url: str | None
    duration: float
    model_name: str | None = None
    model_version: str | None = None
    model_params: dict[str, Any] | None = None

    model_config = {"from_attributes": True}


class SceneListResponse(BaseModel):
    scenes: list[SceneResponse]
    total_scenes: int
    total_duration: float
