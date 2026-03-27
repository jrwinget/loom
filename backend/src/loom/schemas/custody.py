from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel


class CustodyEntryResponse(BaseModel):
    id: UUID
    asset_id: UUID
    action: str
    actor_id: UUID
    detail: Any | None = None
    ip_address: str | None = None
    timestamp: datetime

    model_config = {"from_attributes": True}


class CustodyEntryListResponse(BaseModel):
    items: list[CustodyEntryResponse]
    total: int


class CustodyGap(BaseModel):
    """a gap detected between two consecutive entries."""

    entry_before_id: UUID
    entry_after_id: UUID
    gap_seconds: float
    before_timestamp: datetime
    after_timestamp: datetime


class CustodyIssue(BaseModel):
    """an issue found during chain verification."""

    severity: str  # "error" | "warning"
    description: str
    entry_id: UUID | None = None


class CustodyVerificationResult(BaseModel):
    asset_id: UUID
    is_valid: bool
    entries_count: int
    first_entry: datetime | None = None
    last_entry: datetime | None = None
    gaps: list[CustodyGap] = []
    issues: list[CustodyIssue] = []
    verified_at: datetime


class CaseCustodyVerificationResult(BaseModel):
    case_id: UUID
    total_assets: int
    valid_assets: int
    invalid_assets: int
    results: list[CustodyVerificationResult]
    verified_at: datetime


class CustodyReportResponse(BaseModel):
    """structured custody report suitable for court submission."""

    asset_id: UUID
    original_filename: str
    sha256_hash: str
    sha512_hash: str
    file_size_bytes: int
    media_type: str
    uploaded_at: datetime
    uploaded_by: UUID
    chain: list[CustodyEntryResponse]
    verification: CustodyVerificationResult
    generated_at: datetime
    report_version: str = "1.0"
