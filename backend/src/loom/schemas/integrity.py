from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class IntegrityResult(BaseModel):
    """result of verifying a single asset's integrity."""

    asset_id: UUID
    filename: str
    storage_key: str
    file_size: int
    stored_sha256: str
    computed_sha256: str
    stored_sha512: str
    computed_sha512: str
    sha256_match: bool
    sha512_match: bool
    verified_at: datetime

    @property
    def passed(self) -> bool:
        return self.sha256_match and self.sha512_match

    model_config = {"from_attributes": True}


class CaseIntegrityResult(BaseModel):
    """aggregate result of verifying all assets in a case."""

    case_id: UUID
    total_assets: int
    verified_count: int
    passed_count: int
    failed_count: int
    results: list[IntegrityResult]

    model_config = {"from_attributes": True}


class CustodyEntryResponse(BaseModel):
    """chain of custody entry for reports."""

    id: UUID
    action: str
    actor_id: UUID
    detail: dict[str, str] | None = None
    ip_address: str | None = None
    timestamp: datetime

    model_config = {"from_attributes": True}


class IntegrityReportResponse(BaseModel):
    """court-ready integrity report for an asset."""

    asset_id: UUID
    case_id: UUID
    original_filename: str
    storage_key: str
    media_type: str
    mime_type: str
    file_size_bytes: int
    uploaded_by: UUID
    uploaded_at: datetime
    verification: IntegrityResult
    custody_chain: list[CustodyEntryResponse]
    report_generated_at: datetime

    model_config = {"from_attributes": True}
