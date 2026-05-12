from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID, uuid4

import pytest

from loom.services.correlation import (
    asset_effective_window,
    compute_correlation_candidates,
    decide_candidate,
    fuse_pair_signals,
    geo_proximity_score,
    haversine_meters,
    list_candidates,
    persist_correlation_candidates,
    temporal_confidence,
    windows_overlap,
)

_CASE_ID = "01912345-6789-7abc-8def-0123456789ef"


def _make_asset(
    *,
    asset_id: str | None = None,
    capture_time: datetime | None = None,
    duration_seconds: float | None = None,
    lat: float | None = None,
    lon: float | None = None,
    clock_offset_seconds: float | None = None,
    clock_confidence: float | None = None,
) -> MagicMock:
    """build a stand-in Asset with only the fields this service reads."""
    asset = MagicMock()
    asset.id = UUID(asset_id) if asset_id else uuid4()
    asset.capture_time = capture_time
    asset.capture_location_lat = lat
    asset.capture_location_lon = lon
    asset.clock_offset_seconds = clock_offset_seconds
    asset.clock_confidence = clock_confidence
    asset.metadata_extracted = (
        {"duration_seconds": duration_seconds}
        if duration_seconds is not None
        else None
    )
    return asset


class TestAssetEffectiveWindow:
    def test_returns_none_without_capture_time(self) -> None:
        asset = _make_asset()
        assert asset_effective_window(asset) is None

    def test_photo_defaults_to_one_second_window(self) -> None:
        capture = datetime(2026, 4, 20, 12, 0, 0, tzinfo=UTC)
        asset = _make_asset(capture_time=capture)
        window = asset_effective_window(asset)
        assert window is not None
        start, end = window
        assert start == capture
        assert (end - start).total_seconds() == pytest.approx(1.0)

    def test_uses_duration_when_present(self) -> None:
        capture = datetime(2026, 4, 20, 12, 0, 0, tzinfo=UTC)
        asset = _make_asset(capture_time=capture, duration_seconds=30.0)
        window = asset_effective_window(asset)
        assert window is not None
        start, end = window
        assert (end - start).total_seconds() == pytest.approx(30.0)

    def test_applies_clock_offset(self) -> None:
        capture = datetime(2026, 4, 20, 12, 0, 0, tzinfo=UTC)
        asset = _make_asset(
            capture_time=capture,
            clock_offset_seconds=17.0,
        )
        window = asset_effective_window(asset)
        assert window is not None
        start, _ = window
        assert start == datetime(2026, 4, 20, 12, 0, 17, tzinfo=UTC)

    def test_naive_capture_time_is_treated_as_utc(self) -> None:
        asset = _make_asset(capture_time=datetime(2026, 4, 20, 12, 0, 0))
        window = asset_effective_window(asset)
        assert window is not None
        assert window[0].tzinfo is UTC

    def test_invalid_duration_falls_back_to_photo_window(self) -> None:
        capture = datetime(2026, 4, 20, 12, 0, 0, tzinfo=UTC)
        asset = _make_asset(capture_time=capture)
        asset.metadata_extracted = {"duration_seconds": "not-a-number"}
        window = asset_effective_window(asset)
        assert window is not None
        start, end = window
        assert (end - start).total_seconds() == pytest.approx(1.0)


class TestWindowsOverlap:
    def test_overlap(self) -> None:
        a = (
            datetime(2026, 4, 20, 12, 0, 0, tzinfo=UTC),
            datetime(2026, 4, 20, 12, 0, 10, tzinfo=UTC),
        )
        b = (
            datetime(2026, 4, 20, 12, 0, 5, tzinfo=UTC),
            datetime(2026, 4, 20, 12, 0, 15, tzinfo=UTC),
        )
        assert windows_overlap(a, b) is True

    def test_adjacent_within_tolerance(self) -> None:
        a = (
            datetime(2026, 4, 20, 12, 0, 0, tzinfo=UTC),
            datetime(2026, 4, 20, 12, 0, 10, tzinfo=UTC),
        )
        b = (
            datetime(2026, 4, 20, 12, 0, 13, tzinfo=UTC),
            datetime(2026, 4, 20, 12, 0, 20, tzinfo=UTC),
        )
        assert windows_overlap(a, b, tolerance_seconds=5.0) is True

    def test_gap_exceeds_tolerance(self) -> None:
        a = (
            datetime(2026, 4, 20, 12, 0, 0, tzinfo=UTC),
            datetime(2026, 4, 20, 12, 0, 10, tzinfo=UTC),
        )
        b = (
            datetime(2026, 4, 20, 12, 0, 30, tzinfo=UTC),
            datetime(2026, 4, 20, 12, 0, 40, tzinfo=UTC),
        )
        assert windows_overlap(a, b, tolerance_seconds=5.0) is False

    def test_tolerance_edge_exactly_zero(self) -> None:
        a = (
            datetime(2026, 4, 20, 12, 0, 0, tzinfo=UTC),
            datetime(2026, 4, 20, 12, 0, 10, tzinfo=UTC),
        )
        b = (
            datetime(2026, 4, 20, 12, 0, 10, tzinfo=UTC),
            datetime(2026, 4, 20, 12, 0, 20, tzinfo=UTC),
        )
        assert windows_overlap(a, b, tolerance_seconds=0.0) is True


class TestHaversineMeters:
    def test_identical_points_zero(self) -> None:
        assert haversine_meters(40.7128, -74.0060, 40.7128, -74.0060) == (
            pytest.approx(0.0, abs=1e-6)
        )

    def test_known_manhattan_pair(self) -> None:
        # times square ~ (40.7580, -73.9855) to grand central ~
        # (40.7527, -73.9772) is ~900m in reality; allow 10% slack.
        distance = haversine_meters(40.7580, -73.9855, 40.7527, -73.9772)
        assert 800.0 <= distance <= 1000.0

    def test_symmetric(self) -> None:
        d1 = haversine_meters(40.7580, -73.9855, 40.7527, -73.9772)
        d2 = haversine_meters(40.7527, -73.9772, 40.7580, -73.9855)
        assert d1 == pytest.approx(d2)


class TestGeoProximityScore:
    def test_near_branch(self) -> None:
        a = _make_asset(lat=40.7580, lon=-73.9855)
        b = _make_asset(lat=40.7580, lon=-73.9855)
        assert geo_proximity_score(a, b) == 1.0

    def test_far_branch(self) -> None:
        a = _make_asset(lat=40.7580, lon=-73.9855)
        b = _make_asset(lat=41.8781, lon=-87.6298)  # chicago
        assert geo_proximity_score(a, b) == 0.0

    def test_between_branch_is_linear(self) -> None:
        a = _make_asset(lat=40.7580, lon=-73.9855)
        b = _make_asset(lat=40.7527, lon=-73.9772)  # ~900m
        score = geo_proximity_score(a, b, near_meters=50.0, far_meters=1000.0)
        assert score is not None
        assert 0.0 < score < 0.2

    def test_missing_coords_returns_none(self) -> None:
        a = _make_asset(lat=40.7580, lon=-73.9855)
        b = _make_asset()  # no geo
        assert geo_proximity_score(a, b) is None


class TestTemporalConfidence:
    def test_both_known_takes_min(self) -> None:
        a = _make_asset(clock_confidence=1.0)
        b = _make_asset(clock_confidence=0.5)
        assert temporal_confidence(a, b) == 0.5

    def test_one_known_falls_back(self) -> None:
        a = _make_asset(clock_confidence=1.0)
        b = _make_asset()
        assert temporal_confidence(a, b) == 0.5

    def test_one_known_but_low_still_capped(self) -> None:
        a = _make_asset(clock_confidence=0.1)
        b = _make_asset()
        assert temporal_confidence(a, b) == pytest.approx(0.1)

    def test_neither_known(self) -> None:
        a = _make_asset()
        b = _make_asset()
        assert temporal_confidence(a, b) == pytest.approx(0.3)


class TestFusePairSignals:
    def test_full_agreement(self) -> None:
        t = datetime(2026, 4, 20, 12, 0, 0, tzinfo=UTC)
        a = _make_asset(
            capture_time=t,
            duration_seconds=10.0,
            lat=40.7580,
            lon=-73.9855,
            clock_confidence=1.0,
        )
        b = _make_asset(
            capture_time=t + timedelta(seconds=1),
            duration_seconds=10.0,
            lat=40.7580,
            lon=-73.9855,
            clock_confidence=1.0,
        )
        result = fuse_pair_signals(a, b)
        assert result is not None
        confidence, reasoning = result
        assert confidence == pytest.approx(1.0)
        assert reasoning["temporal"]["score"] == pytest.approx(1.0)
        assert reasoning["geo"]["score"] == pytest.approx(1.0)
        assert reasoning["audio"]["score"] is None
        assert reasoning["visual"]["score"] is None

    def test_disagreement_far_apart(self) -> None:
        t = datetime(2026, 4, 20, 12, 0, 0, tzinfo=UTC)
        a = _make_asset(
            capture_time=t,
            duration_seconds=10.0,
            lat=40.7580,
            lon=-73.9855,
            clock_confidence=1.0,
        )
        b = _make_asset(
            capture_time=t + timedelta(seconds=1),
            duration_seconds=10.0,
            lat=41.8781,
            lon=-87.6298,
            clock_confidence=1.0,
        )
        result = fuse_pair_signals(a, b)
        assert result is not None
        confidence, reasoning = result
        assert reasoning["geo"]["score"] == 0.0
        assert confidence < 1.0

    def test_missing_geo_preserves_temporal_only(self) -> None:
        t = datetime(2026, 4, 20, 12, 0, 0, tzinfo=UTC)
        a = _make_asset(
            capture_time=t,
            duration_seconds=10.0,
            clock_confidence=1.0,
        )
        b = _make_asset(
            capture_time=t + timedelta(seconds=1),
            duration_seconds=10.0,
            clock_confidence=1.0,
        )
        result = fuse_pair_signals(a, b)
        assert result is not None
        confidence, reasoning = result
        assert reasoning["geo"]["score"] is None
        assert confidence == pytest.approx(1.0)

    def test_no_overlap_returns_none(self) -> None:
        a = _make_asset(
            capture_time=datetime(2026, 4, 20, 12, 0, 0, tzinfo=UTC),
            duration_seconds=1.0,
        )
        b = _make_asset(
            capture_time=datetime(2026, 4, 20, 12, 5, 0, tzinfo=UTC),
            duration_seconds=1.0,
        )
        assert fuse_pair_signals(a, b) is None

    def test_missing_capture_time_returns_none(self) -> None:
        a = _make_asset(
            capture_time=datetime(2026, 4, 20, 12, 0, 0, tzinfo=UTC),
        )
        b = _make_asset()
        assert fuse_pair_signals(a, b) is None


class TestComputeCorrelationCandidates:
    async def test_groups_correlated_and_excludes_loners(self) -> None:
        # two assets at noon correlate, a third at 3pm is isolated.
        t = datetime(2026, 4, 20, 12, 0, 0, tzinfo=UTC)
        a1 = _make_asset(
            asset_id="00000000-0000-0000-0000-000000000001",
            capture_time=t,
            duration_seconds=5.0,
            lat=40.7580,
            lon=-73.9855,
            clock_confidence=1.0,
        )
        a2 = _make_asset(
            asset_id="00000000-0000-0000-0000-000000000002",
            capture_time=t + timedelta(seconds=1),
            duration_seconds=5.0,
            lat=40.7580,
            lon=-73.9855,
            clock_confidence=1.0,
        )
        a3 = _make_asset(
            asset_id="00000000-0000-0000-0000-000000000003",
            capture_time=t + timedelta(hours=3),
            duration_seconds=5.0,
            lat=40.7580,
            lon=-73.9855,
            clock_confidence=1.0,
        )

        session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [a1, a2, a3]
        session.execute = AsyncMock(return_value=mock_result)

        candidates = await compute_correlation_candidates(session, _CASE_ID)

        assert len(candidates) == 1
        candidate = candidates[0]
        assert set(candidate["asset_ids"]) == {
            str(a1.id),
            str(a2.id),
        }
        assert candidate["confidence"] == pytest.approx(1.0)
        assert candidate["start_utc"] == t
        assert candidate["end_utc"] >= t + timedelta(seconds=5)

    async def test_empty_case_returns_empty(self) -> None:
        session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        session.execute = AsyncMock(return_value=mock_result)
        assert await compute_correlation_candidates(session, _CASE_ID) == []

    async def test_single_asset_returns_empty(self) -> None:
        t = datetime(2026, 4, 20, 12, 0, 0, tzinfo=UTC)
        asset = _make_asset(capture_time=t)
        session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [asset]
        session.execute = AsyncMock(return_value=mock_result)
        assert await compute_correlation_candidates(session, _CASE_ID) == []


class TestPersistCorrelationCandidates:
    async def test_inserts_new_candidates(self) -> None:
        session = AsyncMock()
        session.add = MagicMock()
        session.flush = AsyncMock()
        session.delete = AsyncMock()

        # first execute → existing pending (empty)
        mock_existing = MagicMock()
        mock_existing.scalars.return_value.all.return_value = []
        session.execute = AsyncMock(return_value=mock_existing)

        t = datetime(2026, 4, 20, 12, 0, 0, tzinfo=UTC)
        candidates: list[dict[str, Any]] = [
            {
                "asset_ids": [
                    "00000000-0000-0000-0000-000000000001",
                    "00000000-0000-0000-0000-000000000002",
                ],
                "start_utc": t,
                "end_utc": t + timedelta(seconds=10),
                "confidence": 0.87,
                "reasoning": {"pairs": {}},
            }
        ]

        created = await persist_correlation_candidates(
            session, _CASE_ID, candidates
        )

        assert len(created) == 1
        # 1 candidate row + 2 members = 3 adds
        assert session.add.call_count == 3
        # delete never invoked because no pending existed
        session.delete.assert_not_awaited()

    async def test_replaces_pending_but_preserves_accepted(self) -> None:
        session = AsyncMock()
        session.add = MagicMock()
        session.flush = AsyncMock()

        stale = MagicMock()
        stale.status = "pending"

        mock_existing = MagicMock()
        mock_existing.scalars.return_value.all.return_value = [stale]
        session.execute = AsyncMock(return_value=mock_existing)
        session.delete = AsyncMock()

        t = datetime(2026, 4, 20, 12, 0, 0, tzinfo=UTC)
        await persist_correlation_candidates(
            session,
            _CASE_ID,
            [
                {
                    "asset_ids": [
                        "00000000-0000-0000-0000-000000000001",
                        "00000000-0000-0000-0000-000000000002",
                    ],
                    "start_utc": t,
                    "end_utc": t + timedelta(seconds=10),
                    "confidence": 0.9,
                    "reasoning": {"pairs": {}},
                }
            ],
        )

        # only the pending row is deleted; the query filter is the
        # only thing protecting accepted/rejected rows.
        session.delete.assert_awaited_once_with(stale)

    async def test_empty_candidate_list_still_clears_pending(
        self,
    ) -> None:
        session = AsyncMock()
        session.add = MagicMock()
        session.flush = AsyncMock()

        stale = MagicMock()
        mock_existing = MagicMock()
        mock_existing.scalars.return_value.all.return_value = [stale]
        session.execute = AsyncMock(return_value=mock_existing)
        session.delete = AsyncMock()

        result = await persist_correlation_candidates(session, _CASE_ID, [])
        assert result == []
        session.delete.assert_awaited_once_with(stale)
        session.add.assert_not_called()


class TestDecideCandidate:
    async def test_accepts_pending(self) -> None:
        candidate = MagicMock()
        candidate.status = "pending"
        candidate.decided_by = None
        candidate.decided_at = None

        session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = candidate
        session.execute = AsyncMock(return_value=mock_result)
        session.flush = AsyncMock()

        user_id = str(uuid4())
        cid = "00000000-0000-0000-0000-000000000010"
        updated = await decide_candidate(session, cid, user_id, "accepted")

        assert updated.status == "accepted"
        assert updated.decided_by == UUID(user_id)
        assert updated.decided_at is not None
        session.flush.assert_awaited_once()

    async def test_rejects_pending(self) -> None:
        candidate = MagicMock()
        candidate.status = "pending"

        session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = candidate
        session.execute = AsyncMock(return_value=mock_result)
        session.flush = AsyncMock()

        updated = await decide_candidate(
            session,
            "00000000-0000-0000-0000-000000000010",
            str(uuid4()),
            "rejected",
        )
        assert updated.status == "rejected"

    async def test_bad_status_raises(self) -> None:
        session = AsyncMock()
        with pytest.raises(ValueError, match="invalid status"):
            await decide_candidate(
                session,
                "00000000-0000-0000-0000-000000000010",
                str(uuid4()),
                "archived",
            )

    async def test_missing_candidate_raises(self) -> None:
        session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        session.execute = AsyncMock(return_value=mock_result)

        with pytest.raises(ValueError, match="not found"):
            await decide_candidate(
                session,
                "00000000-0000-0000-0000-000000000010",
                str(uuid4()),
                "accepted",
            )

    async def test_idempotent_reassert_same_status(self) -> None:
        candidate = MagicMock()
        candidate.status = "accepted"

        session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = candidate
        session.execute = AsyncMock(return_value=mock_result)
        session.flush = AsyncMock()

        updated = await decide_candidate(
            session,
            "00000000-0000-0000-0000-000000000010",
            str(uuid4()),
            "accepted",
        )
        assert updated is candidate
        session.flush.assert_not_awaited()

    async def test_cannot_change_decided_candidate(self) -> None:
        candidate = MagicMock()
        candidate.status = "accepted"

        session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = candidate
        session.execute = AsyncMock(return_value=mock_result)

        with pytest.raises(ValueError, match="already decided"):
            await decide_candidate(
                session,
                "00000000-0000-0000-0000-000000000010",
                str(uuid4()),
                "rejected",
            )


class TestListCandidates:
    async def test_attaches_members_to_each_candidate(self) -> None:
        candidate = MagicMock()
        candidate.id = uuid4()

        member = MagicMock()
        member.candidate_id = candidate.id

        session = AsyncMock()
        candidate_result = MagicMock()
        candidate_result.scalars.return_value.all.return_value = [candidate]
        member_result = MagicMock()
        member_result.scalars.return_value.all.return_value = [member]
        session.execute = AsyncMock(
            side_effect=[candidate_result, member_result]
        )

        results = await list_candidates(session, _CASE_ID)
        assert len(results) == 1
        assert results[0].members == [member]  # type: ignore[attr-defined]

    async def test_invalid_status_raises(self) -> None:
        session = AsyncMock()
        with pytest.raises(ValueError, match="invalid status"):
            await list_candidates(session, _CASE_ID, status="archived")

    async def test_empty_returns_empty_without_second_query(self) -> None:
        session = AsyncMock()
        candidate_result = MagicMock()
        candidate_result.scalars.return_value.all.return_value = []
        session.execute = AsyncMock(return_value=candidate_result)

        assert await list_candidates(session, _CASE_ID) == []
        assert session.execute.await_count == 1
