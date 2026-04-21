"""tests for find_temporal_clusters pure function."""

from datetime import UTC, datetime, timedelta
from uuid import UUID

from loom.services.clustering import find_temporal_clusters

_ASSET_A = UUID("00000000-0000-0000-0000-000000000001")
_ASSET_B = UUID("00000000-0000-0000-0000-000000000002")
_ASSET_C = UUID("00000000-0000-0000-0000-000000000003")

_BASE = datetime(2025, 6, 1, 12, 0, 0, tzinfo=UTC)


def _item(
    asset_id: UUID,
    offset_seconds: float,
    duration: float = 5.0,
    content_id: UUID | None = None,
    text: str = "test",
) -> dict:
    """helper to build a content item dict."""
    cid = content_id or UUID(
        f"10000000-0000-0000-0000-{int(offset_seconds):012d}"
    )
    start = _BASE + timedelta(seconds=offset_seconds)
    end = start + timedelta(seconds=duration)
    return {
        "asset_id": asset_id,
        "content_type": "transcript",
        "content_id": cid,
        "absolute_time_start": start,
        "absolute_time_end": end,
        "text_preview": text,
    }


def test_two_assets_within_window() -> None:
    """items from two assets within window form 1 cluster."""
    items = [
        _item(_ASSET_A, 0),
        _item(_ASSET_B, 30),
    ]
    result = find_temporal_clusters(items, window_seconds=60)
    assert len(result) == 1
    assert len(result[0]) == 2


def test_two_assets_outside_window() -> None:
    """items from two assets outside window form no cluster."""
    items = [
        _item(_ASSET_A, 0, duration=5),
        _item(_ASSET_B, 200),
    ]
    result = find_temporal_clusters(items, window_seconds=60)
    assert len(result) == 0


def test_same_asset_no_cluster() -> None:
    """items from one asset don't form a cluster."""
    items = [
        _item(_ASSET_A, 0),
        _item(_ASSET_A, 10),
    ]
    result = find_temporal_clusters(items, window_seconds=60)
    assert len(result) == 0


def test_three_assets_chain() -> None:
    """items from 3 assets forming a chain cluster."""
    items = [
        _item(_ASSET_A, 0),
        _item(_ASSET_B, 30),
        _item(_ASSET_C, 55),
    ]
    result = find_temporal_clusters(items, window_seconds=60)
    assert len(result) == 1
    assert len(result[0]) == 3


def test_window_size_affects_results() -> None:
    """smaller window excludes items further apart."""
    items = [
        _item(_ASSET_A, 0, duration=5),
        _item(_ASSET_B, 50),
    ]
    # with window=60, they connect (0+5+60=65 > 50)
    result_wide = find_temporal_clusters(items, window_seconds=60)
    assert len(result_wide) == 1

    # with window=5, they don't connect (0+5+5=10 < 50)
    result_narrow = find_temporal_clusters(items, window_seconds=5)
    assert len(result_narrow) == 0


def test_empty_input() -> None:
    """empty item list returns empty."""
    result = find_temporal_clusters([], window_seconds=60)
    assert result == []


def test_exact_same_time() -> None:
    """items at exact same time from different assets cluster."""
    items = [
        _item(_ASSET_A, 0),
        _item(_ASSET_B, 0),
    ]
    result = find_temporal_clusters(items, window_seconds=60)
    assert len(result) == 1
    assert len(result[0]) == 2


def test_multiple_disjoint_clusters() -> None:
    """two separate groups form two clusters."""
    items = [
        _item(_ASSET_A, 0),
        _item(_ASSET_B, 10),
        _item(_ASSET_A, 500),
        _item(_ASSET_B, 510),
    ]
    result = find_temporal_clusters(items, window_seconds=60)
    assert len(result) == 2
