"""unit tests for loom.services.conflict."""

from unittest.mock import AsyncMock, MagicMock
from uuid import UUID, uuid4

import pytest

from loom.models.conflict import ConflictResolution
from loom.models.timeline import TimelineEvent
from loom.services.conflict import (
    create_resolution,
    get_event_conflicts,
    list_case_conflicts,
    update_resolution,
)

_CASE_ID = str(uuid4())
_EVENT_ID = str(uuid4())
_USER_ID = str(uuid4())
_RES_ID = str(uuid4())


def _mock_session() -> AsyncMock:
    s = AsyncMock()
    s.add = MagicMock()
    s.commit = AsyncMock()
    s.refresh = AsyncMock()
    s.delete = AsyncMock()
    return s


# ── get_event_conflicts ─────────────────────────────────────


class TestGetEventConflicts:
    @pytest.mark.asyncio
    async def test_returns_none_when_event_not_in_case(
        self,
    ) -> None:
        """idor guard: returns none if event not in case."""
        session = _mock_session()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        session.execute.return_value = mock_result

        result = await get_event_conflicts(session, _EVENT_ID, _CASE_ID)
        assert result is None

    @pytest.mark.asyncio
    async def test_returns_conflict_detail(self) -> None:
        """returns supporting/contradicting lists and resolutions."""
        session = _mock_session()
        event = TimelineEvent(
            case_id=UUID(_CASE_ID),
            title="Arrest",
            event_time_start=None,
            created_by=UUID(_USER_ID),
        )
        event.id = UUID(_EVENT_ID)

        # mock evidence rows
        ev_support = MagicMock()
        ev_support.asset_id = uuid4()
        ev_support.annotation_id = None
        ev_support.clip_start = 0.0
        ev_support.clip_end = 5.0
        ev_support.relationship = "supports"
        ev_support.notes = "clear"
        ev_support.id = uuid4()

        ev_contra = MagicMock()
        ev_contra.asset_id = uuid4()
        ev_contra.annotation_id = None
        ev_contra.clip_start = None
        ev_contra.clip_end = None
        ev_contra.relationship = "contradicts"
        ev_contra.notes = "blurry"
        ev_contra.id = uuid4()

        resolution = ConflictResolution(
            event_id=UUID(_EVENT_ID),
            resolution_type="noted",
            resolved_by=UUID(_USER_ID),
        )

        # first execute: event lookup
        event_result = MagicMock()
        event_result.scalar_one_or_none.return_value = event
        # second execute: evidence rows
        evidence_result = MagicMock()
        evidence_result.all.return_value = [
            (ev_support, "video.mp4"),
            (ev_contra, "photo.jpg"),
        ]
        # third execute: resolutions
        res_result = MagicMock()
        res_scalars = MagicMock()
        res_scalars.all.return_value = [resolution]
        res_result.scalars.return_value = res_scalars

        session.execute.side_effect = [
            event_result,
            evidence_result,
            res_result,
        ]

        result = await get_event_conflicts(session, _EVENT_ID, _CASE_ID)
        assert result is not None
        assert result["event_id"] == event.id
        assert result["event_title"] == "Arrest"
        assert len(result["supporting"]) == 1
        assert len(result["contradicting"]) == 1
        assert result["supporting"][0]["original_filename"] == "video.mp4"
        assert result["contradicting"][0]["relationship"] == "contradicts"
        assert len(result["resolutions"]) == 1

    @pytest.mark.asyncio
    async def test_context_evidence_excluded(self) -> None:
        """context-relationship evidence is not in either list."""
        session = _mock_session()
        event = TimelineEvent(
            case_id=UUID(_CASE_ID),
            title="E",
            event_time_start=None,
            created_by=UUID(_USER_ID),
        )
        event.id = UUID(_EVENT_ID)

        ev_context = MagicMock()
        ev_context.relationship = "context"
        ev_context.asset_id = uuid4()
        ev_context.annotation_id = None
        ev_context.clip_start = None
        ev_context.clip_end = None
        ev_context.notes = None
        ev_context.id = uuid4()

        event_result = MagicMock()
        event_result.scalar_one_or_none.return_value = event
        evidence_result = MagicMock()
        evidence_result.all.return_value = [(ev_context, "file.pdf")]
        res_result = MagicMock()
        res_scalars = MagicMock()
        res_scalars.all.return_value = []
        res_result.scalars.return_value = res_scalars

        session.execute.side_effect = [
            event_result,
            evidence_result,
            res_result,
        ]

        result = await get_event_conflicts(session, _EVENT_ID, _CASE_ID)
        assert result["supporting"] == []
        assert result["contradicting"] == []


# ── list_case_conflicts ─────────────────────────────────────


class TestListCaseConflicts:
    @pytest.mark.asyncio
    async def test_returns_conflict_summaries(self) -> None:
        """returns events with both supports and contradicts."""
        session = _mock_session()
        event = TimelineEvent(
            case_id=UUID(_CASE_ID),
            title="Incident",
            event_time_start=None,
            created_by=UUID(_USER_ID),
        )
        event.id = UUID(_EVENT_ID)

        count_result = MagicMock()
        count_result.scalar_one.return_value = 1
        row = MagicMock()
        row.__getitem__ = lambda self, i: [event, 3, 2, 1][i]
        data_result = MagicMock()
        data_result.all.return_value = [row]
        session.execute.side_effect = [count_result, data_result]

        items, total = await list_case_conflicts(session, _CASE_ID)
        assert total == 1
        assert len(items) == 1
        assert items[0]["supporting_count"] == 3
        assert items[0]["contradicting_count"] == 2
        assert items[0]["resolution_count"] == 1
        assert items[0]["is_resolved"] is True
        assert items[0]["event_title"] == "Incident"

    @pytest.mark.asyncio
    async def test_unresolved_items(self) -> None:
        """is_resolved is false when resolution_count is 0."""
        session = _mock_session()
        event = TimelineEvent(
            case_id=UUID(_CASE_ID),
            title="E",
            event_time_start=None,
            created_by=UUID(_USER_ID),
        )
        event.id = UUID(_EVENT_ID)

        count_result = MagicMock()
        count_result.scalar_one.return_value = 1
        row = MagicMock()
        row.__getitem__ = lambda self, i: [event, 1, 1, 0][i]
        data_result = MagicMock()
        data_result.all.return_value = [row]
        session.execute.side_effect = [count_result, data_result]

        items, _ = await list_case_conflicts(session, _CASE_ID)
        assert items[0]["is_resolved"] is False

    @pytest.mark.asyncio
    async def test_empty_result(self) -> None:
        """returns empty list when no conflicting events."""
        session = _mock_session()
        count_result = MagicMock()
        count_result.scalar_one.return_value = 0
        data_result = MagicMock()
        data_result.all.return_value = []
        session.execute.side_effect = [count_result, data_result]

        items, total = await list_case_conflicts(session, _CASE_ID)
        assert total == 0
        assert items == []

    @pytest.mark.asyncio
    async def test_null_counts_default_zero(self) -> None:
        """null subquery counts become 0."""
        session = _mock_session()
        event = TimelineEvent(
            case_id=UUID(_CASE_ID),
            title="E",
            event_time_start=None,
            created_by=UUID(_USER_ID),
        )
        event.id = UUID(_EVENT_ID)

        count_result = MagicMock()
        count_result.scalar_one.return_value = 1
        row = MagicMock()
        row.__getitem__ = lambda self, i: [event, None, None, None][i]
        data_result = MagicMock()
        data_result.all.return_value = [row]
        session.execute.side_effect = [count_result, data_result]

        items, _ = await list_case_conflicts(session, _CASE_ID)
        assert items[0]["supporting_count"] == 0
        assert items[0]["contradicting_count"] == 0
        assert items[0]["resolution_count"] == 0
        assert items[0]["is_resolved"] is False


# ── create_resolution ───────────────────────────────────────


class TestCreateResolution:
    @pytest.mark.asyncio
    async def test_creates_resolution(self) -> None:
        """creates resolution record for event in case."""
        session = _mock_session()
        event = TimelineEvent(
            case_id=UUID(_CASE_ID),
            title="E",
            event_time_start=None,
            created_by=UUID(_USER_ID),
        )
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = event
        session.execute.return_value = mock_result

        data = {
            "resolution_type": "accepted_supporting",
            "notes": "video is definitive",
        }
        result = await create_resolution(
            session, _EVENT_ID, _CASE_ID, data, _USER_ID
        )
        assert isinstance(result, ConflictResolution)
        assert result.event_id == UUID(_EVENT_ID)
        assert result.resolution_type == "accepted_supporting"
        assert result.notes == "video is definitive"
        assert result.resolved_by == UUID(_USER_ID)
        session.add.assert_called_once()
        session.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_raises_when_event_not_in_case(self) -> None:
        """raises ValueError if event not found in case."""
        session = _mock_session()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        session.execute.return_value = mock_result

        with pytest.raises(ValueError, match="event not found"):
            await create_resolution(
                session,
                _EVENT_ID,
                _CASE_ID,
                {"resolution_type": "noted"},
                _USER_ID,
            )

    @pytest.mark.asyncio
    async def test_notes_optional(self) -> None:
        """notes field defaults to none."""
        session = _mock_session()
        event = TimelineEvent(
            case_id=UUID(_CASE_ID),
            title="E",
            event_time_start=None,
            created_by=UUID(_USER_ID),
        )
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = event
        session.execute.return_value = mock_result

        result = await create_resolution(
            session,
            _EVENT_ID,
            _CASE_ID,
            {"resolution_type": "dismissed"},
            _USER_ID,
        )
        assert result.notes is None


# ── update_resolution ───────────────────────────────────────


class TestUpdateResolution:
    @pytest.mark.asyncio
    async def test_updates_resolution(self) -> None:
        """partial update on resolution fields."""
        session = _mock_session()
        resolution = ConflictResolution(
            event_id=UUID(_EVENT_ID),
            resolution_type="noted",
            notes="old",
            resolved_by=UUID(_USER_ID),
        )
        event = TimelineEvent(
            case_id=UUID(_CASE_ID),
            title="E",
            event_time_start=None,
            created_by=UUID(_USER_ID),
        )

        # first: resolution lookup
        res_result = MagicMock()
        res_result.scalar_one_or_none.return_value = resolution
        # second: event verification
        ev_result = MagicMock()
        ev_result.scalar_one_or_none.return_value = event
        session.execute.side_effect = [res_result, ev_result]

        updated = await update_resolution(
            session,
            _RES_ID,
            _CASE_ID,
            {"notes": "updated analysis", "resolution_type": None},
        )
        assert updated is not None
        assert updated.notes == "updated analysis"
        # resolution_type stays (none skipped)
        assert updated.resolution_type == "noted"
        session.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_returns_none_when_resolution_missing(
        self,
    ) -> None:
        """returns none if resolution not found."""
        session = _mock_session()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        session.execute.return_value = mock_result

        result = await update_resolution(
            session, _RES_ID, _CASE_ID, {"notes": "x"}
        )
        assert result is None

    @pytest.mark.asyncio
    async def test_returns_none_when_event_wrong_case(
        self,
    ) -> None:
        """idor guard: returns none if event not in case."""
        session = _mock_session()
        resolution = ConflictResolution(
            event_id=UUID(_EVENT_ID),
            resolution_type="noted",
            resolved_by=UUID(_USER_ID),
        )
        # resolution found
        res_result = MagicMock()
        res_result.scalar_one_or_none.return_value = resolution
        # event not in case
        ev_result = MagicMock()
        ev_result.scalar_one_or_none.return_value = None
        session.execute.side_effect = [res_result, ev_result]

        result = await update_resolution(
            session, _RES_ID, _CASE_ID, {"notes": "x"}
        )
        assert result is None
        session.commit.assert_not_awaited()
