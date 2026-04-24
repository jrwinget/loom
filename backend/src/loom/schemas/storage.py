"""schemas for the lite-profile storage management endpoints.

exposes usage stats for Settings -> Storage, a pre-ingest free-space
check for the batch-picker flow, and the relocation job envelope
used by the data-directory move wizard. see issue #47.
"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class StorageUsage(BaseModel):
    """snapshot of the lite-profile data directory footprint."""

    data_dir: str
    free_bytes: int
    total_bytes: int
    originals_bytes: int
    derivatives_bytes: int
    db_bytes: int
    logs_bytes: int
    asset_count: int
    # true when the data dir lives on the same drive as the OS —
    # triggers a "move to external" advisory for field installs.
    on_system_drive: bool


class StorageCheckRequest(BaseModel):
    """ask whether ``path`` has room for a planned ingest batch."""

    path: str
    estimated_batch_size: int = Field(ge=0)


class StorageCheckResponse(BaseModel):
    writable: bool
    writable_reason: str | None = None
    free_bytes: int
    total_bytes: int
    on_system_drive: bool
    advisory: Literal["proceed", "warning", "blocked"]
    advisory_reason: str | None = None


class RelocationRequest(BaseModel):
    target_path: str


class RelocationJobStatus(BaseModel):
    job_id: str
    status: Literal["running", "completed", "failed"]
    assets_copied: int
    assets_total: int
    bytes_copied: int
    bytes_total: int
    error: str | None = None
    started_at: datetime
    completed_at: datetime | None = None


class RelocationStartResponse(BaseModel):
    job_id: str
