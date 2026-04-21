from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID, uuid4

import pytest

from loom.services.clock_drift import (
    CONFIDENCE_AGREE,
    CONFIDENCE_DISAGREE,
    CONFIDENCE_PARTIAL,
    apply_clock_anchor,
    detect_clock_drift,
    parse_filename_timestamp,
    parse_metadata_timestamp,
)


class TestParseFilenameTimestamp:
    @pytest.mark.parametrize(
        "filename,expected",
        [
            ("IMG_20260420_120000.jpg", datetime(2026, 4, 20, 12, 0, 0)),
            ("VID_20260420_153045.mp4", datetime(2026, 4, 20, 15, 30, 45)),
            ("PXL_20260420_120000.mp4", datetime(2026, 4, 20, 12, 0, 0)),
            ("2026-04-20_12-00-00.mov", datetime(2026, 4, 20, 12, 0, 0)),
            ("20260420_120000.jpg", datetime(2026, 4, 20, 12, 0, 0)),
        ],
    )
    def test_recognizes_common_patterns(
        self, filename: str, expected: datetime
    ) -> None:
        result = parse_filename_timestamp(filename)
        assert result is not None
        assert result.replace(tzinfo=None) == expected

    def test_returns_none_when_no_pattern_matches(self) -> None:
        assert parse_filename_timestamp("photo.jpg") is None
        assert parse_filename_timestamp("random_file.mp4") is None

    def test_ignores_path_prefix(self) -> None:
        # path prefix is irrelevant — only the basename is scanned
        result = parse_filename_timestamp(
            "/cases/evidence/IMG_20260420_120000.jpg"
        )
        assert result is not None
        assert result.year == 2026


class TestParseMetadataTimestamp:
    def test_parses_iso_with_z_suffix(self) -> None:
        result = parse_metadata_timestamp("2026-04-20T12:00:00Z")
        assert result == datetime(2026, 4, 20, 12, 0, 0, tzinfo=UTC)

    def test_parses_naive_as_utc(self) -> None:
        result = parse_metadata_timestamp("2026-04-20T12:00:00")
        assert result is not None
        assert result.tzinfo is UTC

    def test_returns_none_for_non_string(self) -> None:
        assert parse_metadata_timestamp(None) is None
        assert parse_metadata_timestamp(12345) is None

    def test_returns_none_for_unparseable(self) -> None:
        assert parse_metadata_timestamp("not a date") is None

    def test_strips_excessive_fractional_seconds(self) -> None:
        result = parse_metadata_timestamp("2026-04-20T12:00:00.123456789Z")
        assert result is not None
        assert result.year == 2026


class TestDetectClockDrift:
    def test_single_source_yields_none_confidence(self) -> None:
        result = detect_clock_drift(
            "IMG_20260420_120000.jpg",
            raw_metadata={},
        )
        assert result["confidence"] is None
        assert result["max_delta_seconds"] is None

    def test_all_sources_agreeing_returns_high(self) -> None:
        result = detect_clock_drift(
            "IMG_20260420_120000.jpg",
            raw_metadata={
                "capture_time_utc": "2026-04-20T12:00:01Z",
                "exif_datetime_original": "2026-04-20T12:00:00Z",
            },
        )
        assert result["confidence"] == CONFIDENCE_AGREE

    def test_moderate_disagreement_returns_partial(self) -> None:
        result = detect_clock_drift(
            "IMG_20260420_120000.jpg",
            raw_metadata={"capture_time_utc": "2026-04-20T12:02:00Z"},
        )
        assert result["confidence"] == CONFIDENCE_PARTIAL
        assert result["max_delta_seconds"] == pytest.approx(120.0)

    def test_strong_disagreement_returns_low(self) -> None:
        result = detect_clock_drift(
            "IMG_20260420_120000.jpg",
            raw_metadata={"capture_time_utc": "2026-04-20T13:00:00Z"},
        )
        assert result["confidence"] == CONFIDENCE_DISAGREE

    def test_sources_dict_records_what_was_parsed(self) -> None:
        result = detect_clock_drift(
            "IMG_20260420_120000.jpg",
            raw_metadata={"capture_time_utc": "2026-04-20T12:00:00Z"},
        )
        assert result["sources"]["filename"] is not None
        assert result["sources"]["container"] is not None
        assert result["sources"]["exif"] is None


class TestApplyClockAnchor:
    @pytest.mark.asyncio
    async def test_computes_positive_offset_when_clock_behind(
        self,
    ) -> None:
        # reviewer says "overlay says 12:00:00 but it was actually 12:00:17"
        # → device clock is 17 seconds behind → positive offset
        asset_id = "01912345-6789-7abc-8def-0123456789ab"
        mock_asset = MagicMock()
        mock_asset.id = UUID(asset_id)

        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = mock_asset
        session = AsyncMock()
        session.execute.return_value = result_mock
        session.add = MagicMock()

        updated = await apply_clock_anchor(
            session,
            asset_id,
            reported_time=datetime(
                2026, 4, 20, 12, 0, 0, tzinfo=UTC
            ),
            actual_time=datetime(
                2026, 4, 20, 12, 0, 17, tzinfo=UTC
            ),
            actor_id=str(uuid4()),
            note="overlay off by 17s",
        )

        assert updated.clock_offset_seconds == 17.0
        assert updated.clock_confidence == CONFIDENCE_AGREE

    @pytest.mark.asyncio
    async def test_writes_custody_entry(self) -> None:
        asset_id = "01912345-6789-7abc-8def-0123456789ab"
        mock_asset = MagicMock()
        mock_asset.id = UUID(asset_id)

        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = mock_asset
        session = AsyncMock()
        session.execute.return_value = result_mock
        session.add = MagicMock()

        actor_id = str(uuid4())
        await apply_clock_anchor(
            session,
            asset_id,
            reported_time=datetime(
                2026, 4, 20, 12, 0, 0, tzinfo=UTC
            ),
            actual_time=datetime(
                2026, 4, 20, 12, 0, 0, tzinfo=UTC
            ),
            actor_id=actor_id,
        )

        session.add.assert_called_once()
        entry = session.add.call_args[0][0]
        assert entry.action == "clock_anchor_corrected"
        assert entry.actor_id == UUID(actor_id)
        assert entry.detail["offset_seconds"] == 0.0

    @pytest.mark.asyncio
    async def test_raises_when_asset_missing(self) -> None:
        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = None
        session = AsyncMock()
        session.execute.return_value = result_mock
        session.add = MagicMock()

        with pytest.raises(ValueError, match="not found"):
            await apply_clock_anchor(
                session,
                "01912345-6789-7abc-8def-0123456789ab",
                reported_time=datetime.now(UTC),
                actual_time=datetime.now(UTC) + timedelta(seconds=1),
                actor_id=str(uuid4()),
            )
