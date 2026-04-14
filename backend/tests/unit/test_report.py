from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

_CASE_ID = "01912345-6789-7abc-8def-0123456789ef"
_NOW = datetime(2025, 6, 15, 12, 0, 0, tzinfo=UTC)


def _make_report_data() -> dict:
    """build a sample report data dict."""
    return {
        "case": {
            "name": "Test Case",
            "description": "A test case",
            "status": "active",
        },
        "events": [
            {
                "id": "01912345-6789-7abc-8def-0123456789ab",
                "title": "Protest at City Hall",
                "description": "Large gathering observed",
                "event_time_start": _NOW,
                "event_time_end": None,
                "status": "accepted",
                "location_description": "City Hall steps",
                "supporting": [
                    {
                        "original_filename": "video1.mp4",
                        "clip_start": 10.0,
                        "clip_end": 30.0,
                        "notes": "shows crowd",
                        "relationship": "supports",
                    }
                ],
                "contradicting": [
                    {
                        "original_filename": "photo2.jpg",
                        "clip_start": None,
                        "clip_end": None,
                        "notes": "timestamp mismatch",
                        "relationship": "contradicts",
                    }
                ],
                "context": [],
            }
        ],
        "annotations": [],
        "chain_of_custody": [],
        "assets": [
            {
                "id": "01912345-6789-7abc-8def-0123456789ac",
                "original_filename": "video1.mp4",
                "media_type": "video",
                "sha256_hash": "abc123" * 10 + "abcd",
                "file_size_bytes": 1024000,
            }
        ],
        "generated_at": _NOW.isoformat(),
        "executive_summary": "Summary of events.",
        "date_range_start": None,
        "date_range_end": None,
    }


class TestBuildReportData:
    """build_report_data returns correct structure."""

    async def test_returns_case_info(self) -> None:
        """report data includes case metadata."""
        session = AsyncMock()

        # mock case query
        case_mock = MagicMock()
        case_mock.name = "Test Case"
        case_mock.description = "desc"
        case_mock.status = "active"

        # mock empty results for other queries
        empty_scalars = MagicMock()
        empty_scalars.scalars.return_value.all.return_value = []

        case_result = MagicMock()
        case_result.scalar_one_or_none.return_value = case_mock

        session.execute.side_effect = [
            case_result,  # case query
            empty_scalars,  # events query
            empty_scalars,  # assets query
            empty_scalars,  # annotations query
        ]

        from loom.services.report import build_report_data

        result = await build_report_data(session, _CASE_ID, {})
        assert result["case"]["name"] == "Test Case"
        assert "events" in result
        assert "assets" in result
        assert "generated_at" in result

    async def test_filters_by_event_ids(self) -> None:
        """event_ids option narrows event query."""
        session = AsyncMock()

        case_mock = MagicMock()
        case_mock.name = "Case"
        case_mock.description = None
        case_mock.status = "active"

        empty_scalars = MagicMock()
        empty_scalars.scalars.return_value.all.return_value = []

        case_result = MagicMock()
        case_result.scalar_one_or_none.return_value = case_mock

        session.execute.side_effect = [
            case_result,
            empty_scalars,
            empty_scalars,
            empty_scalars,
        ]

        from loom.services.report import build_report_data

        result = await build_report_data(
            session,
            _CASE_ID,
            {"event_ids": ["01912345-6789-7abc-8def-0123456789ab"]},
        )
        # should complete without error; event list may be empty
        assert isinstance(result["events"], list)

    async def test_date_range_filtering(self) -> None:
        """date range options are applied."""
        session = AsyncMock()

        case_mock = MagicMock()
        case_mock.name = "Case"
        case_mock.description = None
        case_mock.status = "active"

        empty_scalars = MagicMock()
        empty_scalars.scalars.return_value.all.return_value = []

        case_result = MagicMock()
        case_result.scalar_one_or_none.return_value = case_mock

        session.execute.side_effect = [
            case_result,
            empty_scalars,
            empty_scalars,
            empty_scalars,
        ]

        from loom.services.report import build_report_data

        result = await build_report_data(
            session,
            _CASE_ID,
            {
                "date_range_start": _NOW,
                "date_range_end": _NOW,
            },
        )
        assert result["date_range_start"] == _NOW.isoformat()


class TestRenderReportHtml:
    """render_report_html produces valid html."""

    def test_renders_event_sections(self) -> None:
        """html contains event title and evidence."""
        from loom.services.report import render_report_html

        data = _make_report_data()
        html = render_report_html(data)

        assert "Protest at City Hall" in html
        assert "video1.mp4" in html
        assert "Evidence Report" in html

    def test_renders_executive_summary(self) -> None:
        """html includes executive summary text."""
        from loom.services.report import render_report_html

        data = _make_report_data()
        html = render_report_html(data)
        assert "Summary of events." in html

    def test_renders_default_summary(self) -> None:
        """html shows placeholder when no summary."""
        from loom.services.report import render_report_html

        data = _make_report_data()
        data["executive_summary"] = None
        html = render_report_html(data)
        assert "To be completed by analyst." in html

    def test_renders_contradicting_evidence(self) -> None:
        """contradicting evidence appears in html."""
        from loom.services.report import render_report_html

        data = _make_report_data()
        html = render_report_html(data)
        assert "Contradicting Evidence" in html
        assert "timestamp mismatch" in html

    def test_renders_evidence_index(self) -> None:
        """evidence index table is rendered."""
        from loom.services.report import render_report_html

        data = _make_report_data()
        html = render_report_html(data)
        assert "Evidence Index" in html

    def test_empty_events(self) -> None:
        """html renders cleanly with no events."""
        from loom.services.report import render_report_html

        data = _make_report_data()
        data["events"] = []
        html = render_report_html(data)
        assert "No timeline events" in html

    def test_is_valid_html(self) -> None:
        """output starts with doctype declaration."""
        from loom.services.report import render_report_html

        data = _make_report_data()
        html = render_report_html(data)
        assert html.strip().startswith("<!DOCTYPE html>")


class TestRenderReportPdf:
    """render_report_pdf handles missing weasyprint."""

    def test_missing_weasyprint_raises(self) -> None:
        """import error raised when weasyprint absent."""
        from loom.services.report import render_report_pdf

        with (
            patch.dict("sys.modules", {"weasyprint": None}),
            pytest.raises(ImportError, match="weasyprint"),
        ):
            render_report_pdf("<html></html>")

    def test_with_mock_weasyprint(self) -> None:
        """pdf bytes returned when weasyprint available."""
        mock_html_cls = MagicMock()
        mock_html_cls.return_value.write_pdf.return_value = b"%PDF-1.4"

        mock_weasyprint = MagicMock()
        mock_weasyprint.HTML = mock_html_cls

        with patch.dict("sys.modules", {"weasyprint": mock_weasyprint}):
            from loom.services.report import render_report_pdf

            result = render_report_pdf("<html></html>")
            assert result == b"%PDF-1.4"


class TestGenerateReport:
    """generate_report orchestrates the pipeline."""

    async def test_returns_html_and_empty_pdf(self) -> None:
        """returns html and empty bytes when no weasyprint."""
        from loom.services.report import generate_report

        mock_data = _make_report_data()

        with (
            patch(
                "loom.services.report.build_report_data",
                new_callable=AsyncMock,
                return_value=mock_data,
            ),
            patch(
                "loom.services.report.render_report_html",
                return_value="<html>test</html>",
            ),
            patch(
                "loom.services.report.render_report_pdf",
                side_effect=ImportError("no weasyprint"),
            ),
        ):
            session = AsyncMock()
            html, pdf = await generate_report(session, _CASE_ID, {})
            assert html == "<html>test</html>"
            assert pdf == b""
