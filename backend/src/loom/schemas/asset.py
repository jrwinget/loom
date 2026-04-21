from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel


class AssetUploadResponse(BaseModel):
    id: UUID
    original_filename: str
    media_type: str
    sha256_hash: str
    upload_status: str
    processing_status: str

    model_config = {"from_attributes": True}


class AssetResponse(BaseModel):
    id: UUID
    case_id: UUID
    original_filename: str
    storage_key: str
    media_type: str
    mime_type: str
    file_size_bytes: int
    sha256_hash: str
    sha512_hash: str
    upload_status: str
    uploaded_by: UUID
    uploaded_at: datetime
    metadata_raw: Any | None = None
    metadata_extracted: Any | None = None
    capture_time: datetime | None = None
    capture_location_lat: float | None = None
    capture_location_lon: float | None = None
    processing_status: str
    created_at: datetime
    updated_at: datetime
    deleted_at: datetime | None = None
    deleted_by: UUID | None = None

    model_config = {"from_attributes": True}


class AssetListResponse(BaseModel):
    items: list[AssetResponse]
    total: int


class PresignedUrlResponse(BaseModel):
    url: str
    key: str


class PresignedUrlRequest(BaseModel):
    filename: str
    content_type: str
