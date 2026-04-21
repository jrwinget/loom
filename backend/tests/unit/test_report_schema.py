"""tests for report schemas."""

from datetime import UTC, datetime

from loom.schemas.report import ReportRequest, ReportResponse


class TestReportRequest:
    """ReportRequest schema validation."""

    def test_defaults(self) -> None:
        """defaults applied when no fields provided."""
        req = ReportRequest()
        assert req.event_ids is None
        assert req.date_range_start is None
        assert req.date_range_end is None
        assert req.executive_summary is None
        assert req.include_evidence is True
        assert req.include_contradictions is True
        assert req.include_custody is False

    def test_with_all_fields(self) -> None:
        """all fields accepted."""
        now = datetime(2025, 6, 1, tzinfo=UTC)
        req = ReportRequest(
            event_ids=["id1", "id2"],
            date_range_start=now,
            date_range_end=now,
            executive_summary="summary",
            include_evidence=False,
            include_contradictions=False,
            include_custody=True,
        )
        assert req.event_ids == ["id1", "id2"]
        assert req.include_custody is True

    def test_serialization(self) -> None:
        """model can be serialized to dict."""
        req = ReportRequest(include_evidence=False)
        data = req.model_dump()
        assert data["include_evidence"] is False


class TestReportResponse:
    """ReportResponse schema validation."""

    def test_basic_fields(self) -> None:
        """required fields accepted."""
        resp = ReportResponse(export_id="abc", status="pending")
        assert resp.export_id == "abc"
        assert resp.status == "pending"

    def test_serialization(self) -> None:
        """model serializes correctly."""
        resp = ReportResponse(export_id="x", status="complete")
        data = resp.model_dump()
        assert data["export_id"] == "x"
        assert data["status"] == "complete"
