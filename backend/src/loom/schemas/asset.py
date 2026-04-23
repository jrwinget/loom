from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, HttpUrl


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
    clock_offset_seconds: float | None = None
    clock_confidence: float | None = None
    processing_status: str
    created_at: datetime
    updated_at: datetime
    deleted_at: datetime | None = None
    deleted_by: UUID | None = None
    source_uri: str | None = None
    source_canonical_uri: str | None = None
    source_method: str | None = None
    source_downloader: str | None = None
    source_downloader_version: str | None = None
    source_retrieved_at: datetime | None = None
    source_response_headers: Any | None = None
    source_wayback_url: str | None = None
    source_extractor_info: Any | None = None

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


class ClockAnchorRequest(BaseModel):
    # the time the device claims in its own timeline (exif, overlay,
    # or filename timestamp the reviewer is anchoring against)
    reported_time: datetime
    # the ground-truth time the reviewer asserts it actually was
    actual_time: datetime
    # free-form context recorded into chain-of-custody
    note: str | None = None


class ClockAnchorResponse(BaseModel):
    asset_id: UUID
    clock_offset_seconds: float
    clock_confidence: float

    model_config = {"from_attributes": True}


class IngestUrlRequest(BaseModel):
    url: HttpUrl
    submission_note: str | None = None


class IngestUrlResponse(BaseModel):
    asset_id: UUID
    workflow_id: str
    status: Literal["queued"]
