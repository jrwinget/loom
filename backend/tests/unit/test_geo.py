from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID

import pytest

from loom.schemas.geo import (
    GeoAssetResponse,
    GeoBoundsResponse,
    GeoEventResponse,
)

_CASE_ID = "01912345-6789-7abc-8def-0123456789ef"
_NOW = datetime(2025, 6, 15, 12, 0, 0, tzinfo=UTC)


class TestGeoSchemas:
    """schema validation for geo responses."""

    def test_geo_asset_response(self) -> None:
        """geo asset response accepts valid data."""
        resp = GeoAssetResponse(
            id=UUID("01912345-6789-7abc-8def-0123456789ab"),
            original_filename="photo.jpg",
            media_type="image",
            lat=40.7128,
            lon=-74.0060,
            capture_time=_NOW,
        )
        assert resp.lat == 40.7128
        assert resp.lon == -74.0060

    def test_geo_asset_response_null_time(self) -> None:
        """capture_time can be none."""
        resp = GeoAssetResponse(
            id=UUID("01912345-6789-7abc-8def-0123456789ab"),
            original_filename="photo.jpg",
            media_type="image",
            lat=40.7128,
            lon=-74.0060,
            capture_time=None,
        )
        assert resp.capture_time is None

    def test_geo_event_response(self) -> None:
        """geo event response accepts valid data."""
        resp = GeoEventResponse(
            id=UUID("01912345-6789-7abc-8def-0123456789ab"),
            title="Protest at City Hall",
            status="accepted",
            lat=40.7128,
            lon=-74.0060,
            event_time_start=_NOW,
            has_contradictions=True,
        )
        assert resp.has_contradictions is True

    def test_geo_event_response_defaults(self) -> None:
        """has_contradictions defaults to false."""
        resp = GeoEventResponse(
            id=UUID("01912345-6789-7abc-8def-0123456789ab"),
            title="Event",
            status="draft",
            lat=0.0,
            lon=0.0,
            event_time_start=_NOW,
        )
        assert resp.has_contradictions is False

    def test_geo_bounds_response(self) -> None:
        """geo bounds response holds bounding box."""
        resp = GeoBoundsResponse(
            min_lat=40.0,
            max_lat=41.0,
            min_lon=-75.0,
            max_lon=-73.0,
            time_start=_NOW,
            time_end=_NOW,
        )
        assert resp.min_lat == 40.0
        assert resp.max_lon == -73.0

    def test_geo_bounds_null_times(self) -> None:
        """time fields can be none."""
        resp = GeoBoundsResponse(
            min_lat=40.0,
            max_lat=41.0,
            min_lon=-75.0,
            max_lon=-73.0,
            time_start=None,
            time_end=None,
        )
        assert resp.time_start is None


class TestGeoServiceFunctions:
    """service functions with mocked sessions."""

    @pytest.fixture
    def mock_session(self) -> AsyncMock:
        """create a mock async session."""
        return AsyncMock()

    async def test_get_geotagged_assets_empty(
        self, mock_session: AsyncMock
    ) -> None:
        """returns empty list when no geotagged assets."""
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_session.execute.return_value = mock_result

        from loom.services.geo import get_geotagged_assets

        result = await get_geotagged_assets(mock_session, _CASE_ID)
        assert result == []

    async def test_get_geotagged_assets_returns_data(
        self, mock_session: AsyncMock
    ) -> None:
        """returns formatted asset dicts."""
        asset = MagicMock()
        asset.id = UUID("01912345-6789-7abc-8def-0123456789ab")
        asset.original_filename = "photo.jpg"
        asset.media_type = "image"
        asset.capture_location_lat = 40.7128
        asset.capture_location_lon = -74.0060
        asset.capture_time = _NOW

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [asset]
        mock_session.execute.return_value = mock_result

        from loom.services.geo import get_geotagged_assets

        result = await get_geotagged_assets(mock_session, _CASE_ID)
        assert len(result) == 1
        assert result[0]["lat"] == 40.7128
        assert result[0]["original_filename"] == "photo.jpg"

    async def test_get_geotagged_assets_time_filter(
        self, mock_session: AsyncMock
    ) -> None:
        """time filter params are accepted without error."""
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_session.execute.return_value = mock_result

        from loom.services.geo import get_geotagged_assets

        start = datetime(2025, 1, 1, tzinfo=UTC)
        end = datetime(2025, 12, 31, tzinfo=UTC)
        result = await get_geotagged_assets(mock_session, _CASE_ID, start, end)
        assert result == []
        # verify execute was called (query was built)
        mock_session.execute.assert_called_once()

    async def test_get_geotagged_events_empty(
        self, mock_session: AsyncMock
    ) -> None:
        """returns empty list for case with no geotagged events."""
        mock_result = MagicMock()
        mock_result.all.return_value = []
        mock_session.execute.return_value = mock_result

        from loom.services.geo import get_geotagged_events

        result = await get_geotagged_events(mock_session, _CASE_ID)
        assert result == []

    async def test_get_geotagged_events_returns_data(
        self, mock_session: AsyncMock
    ) -> None:
        """returns formatted event dicts with contradiction flag."""
        event = MagicMock()
        event.id = UUID("01912345-6789-7abc-8def-0123456789ab")
        event.title = "Protest"
        event.status = "accepted"
        event.location_lat = 40.7128
        event.location_lon = -74.0060
        event.event_time_start = _NOW

        # row = (event, supports_count, contradicts_count)
        mock_result = MagicMock()
        mock_result.all.return_value = [(event, 2, 1)]
        mock_session.execute.return_value = mock_result

        from loom.services.geo import get_geotagged_events

        result = await get_geotagged_events(mock_session, _CASE_ID)
        assert len(result) == 1
        assert result[0]["has_contradictions"] is True
        assert result[0]["title"] == "Protest"

    async def test_get_geotagged_events_no_contradictions(
        self, mock_session: AsyncMock
    ) -> None:
        """has_contradictions is false when no contradicts."""
        event = MagicMock()
        event.id = UUID("01912345-6789-7abc-8def-0123456789ab")
        event.title = "Event"
        event.status = "draft"
        event.location_lat = 40.0
        event.location_lon = -74.0
        event.event_time_start = _NOW

        mock_result = MagicMock()
        mock_result.all.return_value = [(event, 3, 0)]
        mock_session.execute.return_value = mock_result

        from loom.services.geo import get_geotagged_events

        result = await get_geotagged_events(mock_session, _CASE_ID)
        assert result[0]["has_contradictions"] is False

    async def test_get_geo_bounds_none_when_empty(
        self, mock_session: AsyncMock
    ) -> None:
        """returns none when no geotagged items exist."""
        # both asset and event queries return all-null rows
        empty_row = MagicMock()
        empty_row.__getitem__ = lambda s, i: (
            None,
            None,
            None,
            None,
            None,
            None,
        )[i]

        mock_result = MagicMock()
        mock_result.one.return_value = (
            None,
            None,
            None,
            None,
            None,
            None,
        )
        mock_session.execute.return_value = mock_result

        from loom.services.geo import get_geo_bounds

        result = await get_geo_bounds(mock_session, _CASE_ID)
        assert result is None

    async def test_get_geo_bounds_with_data(
        self, mock_session: AsyncMock
    ) -> None:
        """returns bounding box when data exists."""
        t1 = datetime(2025, 1, 1, tzinfo=UTC)
        t2 = datetime(2025, 6, 1, tzinfo=UTC)

        # first call: asset bounds
        asset_row = (40.0, 41.0, -75.0, -73.0, t1, t2)
        # second call: event bounds
        event_row = (39.5, 40.5, -74.5, -73.5, t1, t2)

        mock_r1 = MagicMock()
        mock_r1.one.return_value = asset_row
        mock_r2 = MagicMock()
        mock_r2.one.return_value = event_row

        mock_session.execute.side_effect = [mock_r1, mock_r2]

        from loom.services.geo import get_geo_bounds

        result = await get_geo_bounds(mock_session, _CASE_ID)
        assert result is not None
        assert result["min_lat"] == 39.5
        assert result["max_lat"] == 41.0
        assert result["min_lon"] == -75.0
        assert result["max_lon"] == -73.0
