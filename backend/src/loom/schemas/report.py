from datetime import datetime

from pydantic import BaseModel


class ReportRequest(BaseModel):
    event_ids: list[str] | None = None
    date_range_start: datetime | None = None
    date_range_end: datetime | None = None
    executive_summary: str | None = None
    include_evidence: bool = True
    include_contradictions: bool = True
    include_custody: bool = False


class ReportResponse(BaseModel):
    export_id: str
    status: str
