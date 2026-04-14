"""unit tests for report schema validation."""

from datetime import UTC, datetime

from loom.schemas.report import ReportRequest, ReportResponse

_NOW = datetime(2025, 6, 1, tzinfo=UTC)


def test_report_request_defaults() -> None:
    """report request optional fields default properly."""
    req = ReportRequest()
    assert req.event_ids is None
    assert req.date_range_start is None
    assert req.date_range_end is None
    assert req.executive_summary is None
    assert req.include_evidence is True
    assert req.include_contradictions is True
    assert req.include_custody is False


def test_report_request_with_all_fields() -> None:
    """report request with all fields validates correctly."""
    req = ReportRequest(
        event_ids=["id-1", "id-2"],
        date_range_start=_NOW,
        date_range_end=_NOW,
        executive_summary="summary text",
        include_evidence=False,
        include_contradictions=False,
        include_custody=True,
    )
    assert len(req.event_ids) == 2
    assert req.executive_summary == "summary text"
    assert req.include_evidence is False
    assert req.include_custody is True


def test_report_request_empty_event_ids() -> None:
    """report request with empty event_ids list is valid."""
    req = ReportRequest(event_ids=[])
    assert req.event_ids == []


def test_report_response_structure() -> None:
    """report response has expected fields."""
    resp = ReportResponse(export_id="abc-123", status="pending")
    assert resp.export_id == "abc-123"
    assert resp.status == "pending"
