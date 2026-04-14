"""unit tests for loom.services.timeline."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID, uuid4

import pytest

from loom.models.timeline import TimelineEvent, TimelineEventEvidence
from loom.services.timeline import (
    create_event,
    get_event,
    get_event_evidence,
    get_timeline,
    link_evidence,
    list_events,
    unlink_evidence,
    update_event,
)

_CASE_ID = str(uuid4())
_USER_ID = str(uuid4())
_EVENT_ID = str(uuid4())
_NOW = datetime(2025, 6, 15, 12, 0, 0, tzinfo=UTC)


def _mock_session() -> AsyncMock:
    s = AsyncMock()
    s.add = MagicMock()
    s.commit = AsyncMock()
    s.flush = AsyncMock()
    s.refresh = AsyncMock()
    s.delete = AsyncMock()
    return s


# ── create_event ────────────────────────────────────────────


class TestCreateEvent:
    @pytest.mark.asyncio
    async def test_creates_event_with_required_fields(self) -> None:
        """stores title, case_id, event_time_start, created_by."""
        session = _mock_session()
        data = {
            "title": "Protest march begins",
            "event_time_start": _NOW,
        }
        result = await create_event(session, _CASE_ID, data, _USER_ID)
        assert isinstance(result, TimelineEvent)
        assert result.title == "Protest march begins"
        assert result.case_id == UUID(_CASE_ID)
        assert result.created_by == UUID(_USER_ID)
        session.add.assert_called_once()
        session.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_defaults_precision_and_status(self) -> None:
        """time_precision defaults to approximate, status to draft."""
        session = _mock_session()
        data = {"title": "E", "event_time_start": _NOW}
        result = await create_event(session, _CASE_ID, data, _USER_ID)
        assert result.time_precision == "approximate"
        assert result.status == "draft"

    @pytest.mark.asyncio
    async def test_all_optional_fields_stored(self) -> None:
        """optional fields are set when provided."""
        session = _mock_session()
        end = datetime(2025, 6, 15, 14, 0, 0, tzinfo=UTC)
        data = {
            "title": "Event",
            "event_time_start": _NOW,
            "event_time_end": end,
            "description": "desc",
            "time_precision": "exact",
            "location_description": "City Hall",
            "location_lat": 45.5,
            "location_lon": -122.6,
            "location_confidence": "gps",
            "status": "confirmed",
        }
        result = await create_event(session, _CASE_ID, data, _USER_ID)
        assert result.event_time_end == end
        assert result.description == "desc"
        assert result.time_precision == "exact"
        assert result.location_lat == 45.5
        assert result.location_confidence == "gps"
        assert result.status == "confirmed"


# ── get_event ───────────────────────────────────────────────


class TestGetEvent:
    @pytest.mark.asyncio
    async def test_returns_event_with_counts(self) -> None:
        """attaches evidence_count and has_contradictions."""
        session = _mock_session()
        event = TimelineEvent(
            case_id=UUID(_CASE_ID),
            title="E",
            event_time_start=_NOW,
            created_by=UUID(_USER_ID),
        )
        row = MagicMock()
        # row[0]=event, row[1]=evidence_count,
        # row[2]=supports, row[3]=contradicts
        row.__getitem__ = lambda self, i: [event, 4, 2, 1][i]
        mock_result = MagicMock()
        mock_result.one_or_none.return_value = row
        session.execute.return_value = mock_result

        got = await get_event(session, _EVENT_ID)
        assert got is event
        assert got.evidence_count == 4
        assert got.has_contradictions is True

    @pytest.mark.asyncio
    async def test_no_contradictions_when_only_supports(self) -> None:
        """has_contradictions false when no contradicts."""
        session = _mock_session()
        event = TimelineEvent(
            case_id=UUID(_CASE_ID),
            title="E",
            event_time_start=_NOW,
            created_by=UUID(_USER_ID),
        )
        row = MagicMock()
        row.__getitem__ = lambda self, i: [event, 2, 2, 0][i]
        mock_result = MagicMock()
        mock_result.one_or_none.return_value = row
        session.execute.return_value = mock_result

        got = await get_event(session, _EVENT_ID)
        assert got.has_contradictions is False

    @pytest.mark.asyncio
    async def test_no_contradictions_when_only_contradicts(
        self,
    ) -> None:
        """has_contradictions false when no supports."""
        session = _mock_session()
        event = TimelineEvent(
            case_id=UUID(_CASE_ID),
            title="E",
            event_time_start=_NOW,
            created_by=UUID(_USER_ID),
        )
        row = MagicMock()
        row.__getitem__ = lambda self, i: [event, 1, 0, 1][i]
        mock_result = MagicMock()
        mock_result.one_or_none.return_value = row
        session.execute.return_value = mock_result

        got = await get_event(session, _EVENT_ID)
        assert got.has_contradictions is False

    @pytest.mark.asyncio
    async def test_returns_none_when_missing(self) -> None:
        """returns none if event not found."""
        session = _mock_session()
        mock_result = MagicMock()
        mock_result.one_or_none.return_value = None
        session.execute.return_value = mock_result

        assert await get_event(session, _EVENT_ID) is None

    @pytest.mark.asyncio
    async def test_null_counts_become_zero(self) -> None:
        """null count values from db default to 0."""
        session = _mock_session()
        event = TimelineEvent(
            case_id=UUID(_CASE_ID),
            title="E",
            event_time_start=_NOW,
            created_by=UUID(_USER_ID),
        )
        row = MagicMock()
        row.__getitem__ = lambda self, i: [event, None, None, None][i]
        mock_result = MagicMock()
        mock_result.one_or_none.return_value = row
        session.execute.return_value = mock_result

        got = await get_event(session, _EVENT_ID)
        assert got.evidence_count == 0
        assert got.has_contradictions is False


# ── list_events ─────────────────────────────────────────────


class TestListEvents:
    @pytest.mark.asyncio
    async def test_returns_paginated_events(self) -> None:
        """returns events list and total count."""
        session = _mock_session()
        event = TimelineEvent(
            case_id=UUID(_CASE_ID),
            title="E",
            event_time_start=_NOW,
            created_by=UUID(_USER_ID),
        )
        count_result = MagicMock()
        count_result.scalar_one.return_value = 1
        row = MagicMock()
        row.__getitem__ = lambda self, i: [event, 2, 1, 1][i]
        data_result = MagicMock()
        data_result.all.return_value = [row]
        session.execute.side_effect = [count_result, data_result]

        events, total = await list_events(session, _CASE_ID, skip=0, limit=50)
        assert total == 1
        assert len(events) == 1
        assert events[0].has_contradictions is True

    @pytest.mark.asyncio
    async def test_empty_result(self) -> None:
        """returns empty list and zero total."""
        session = _mock_session()
        count_result = MagicMock()
        count_result.scalar_one.return_value = 0
        data_result = MagicMock()
        data_result.all.return_value = []
        session.execute.side_effect = [count_result, data_result]

        events, total = await list_events(session, _CASE_ID)
        assert total == 0
        assert events == []

    @pytest.mark.asyncio
    async def test_null_counts_default_zero(self) -> None:
        """null subquery counts become 0."""
        session = _mock_session()
        event = TimelineEvent(
            case_id=UUID(_CASE_ID),
            title="E",
            event_time_start=_NOW,
            created_by=UUID(_USER_ID),
        )
        count_result = MagicMock()
        count_result.scalar_one.return_value = 1
        row = MagicMock()
        row.__getitem__ = lambda self, i: [event, None, None, None][i]
        data_result = MagicMock()
        data_result.all.return_value = [row]
        session.execute.side_effect = [count_result, data_result]

        events, _ = await list_events(session, _CASE_ID)
        assert events[0].evidence_count == 0
        assert events[0].has_contradictions is False


# ── update_event ────────────────────────────────────────────


class TestUpdateEvent:
    @pytest.mark.asyncio
    async def test_partial_update(self) -> None:
        """updates only provided non-none fields."""
        session = _mock_session()
        event = TimelineEvent(
            case_id=UUID(_CASE_ID),
            title="Old",
            description="keep",
            event_time_start=_NOW,
            created_by=UUID(_USER_ID),
        )
        # first call: select for update
        scalar_result = MagicMock()
        scalar_result.scalar_one.return_value = event
        # second call: get_event re-fetch (one_or_none)
        refetch_row = MagicMock()
        refetch_row.__getitem__ = lambda self, i: [event, 0, 0, 0][i]
        refetch_result = MagicMock()
        refetch_result.one_or_none.return_value = refetch_row
        session.execute.side_effect = [scalar_result, refetch_result]

        updated = await update_event(
            session,
            _EVENT_ID,
            {"title": "New", "description": None},
        )
        assert updated.title == "New"
        # description stays because none values are skipped
        assert updated.description == "keep"


# ── link_evidence ───────────────────────────────────────────


class TestLinkEvidence:
    @pytest.mark.asyncio
    async def test_creates_link_with_asset(self) -> None:
        """creates evidence link with asset_id."""
        session = _mock_session()
        asset_id = str(uuid4())
        data = {
            "asset_id": asset_id,
            "relationship": "supports",
            "notes": "clear footage",
        }
        result = await link_evidence(session, _EVENT_ID, data, _USER_ID)
        assert isinstance(result, TimelineEventEvidence)
        assert result.event_id == UUID(_EVENT_ID)
        assert result.asset_id == UUID(asset_id)
        assert result.relationship == "supports"
        assert result.notes == "clear footage"
        assert result.linked_by == UUID(_USER_ID)
        session.add.assert_called_once()

    @pytest.mark.asyncio
    async def test_creates_link_without_optional_ids(self) -> None:
        """asset_id, annotation_id, derivative_id can be none."""
        session = _mock_session()
        data = {"relationship": "contradicts"}
        result = await link_evidence(session, _EVENT_ID, data, _USER_ID)
        assert result.asset_id is None
        assert result.annotation_id is None
        assert result.derivative_id is None

    @pytest.mark.asyncio
    async def test_clip_range_stored(self) -> None:
        """clip_start and clip_end are set when provided."""
        session = _mock_session()
        data = {
            "relationship": "context",
            "clip_start": 10.5,
            "clip_end": 25.0,
        }
        result = await link_evidence(session, _EVENT_ID, data, _USER_ID)
        assert result.clip_start == 10.5
        assert result.clip_end == 25.0


# ── unlink_evidence ─────────────────────────────────────────


class TestUnlinkEvidence:
    @pytest.mark.asyncio
    async def test_deletes_existing_link(self) -> None:
        """returns true and deletes found link."""
        session = _mock_session()
        link = TimelineEventEvidence(
            event_id=UUID(_EVENT_ID),
            relationship="supports",
            linked_by=UUID(_USER_ID),
        )
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = link
        session.execute.return_value = mock_result

        assert await unlink_evidence(session, str(uuid4())) is True
        session.delete.assert_awaited_once_with(link)

    @pytest.mark.asyncio
    async def test_returns_false_when_not_found(self) -> None:
        """returns false when link does not exist."""
        session = _mock_session()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        session.execute.return_value = mock_result

        assert await unlink_evidence(session, str(uuid4())) is False
        session.delete.assert_not_awaited()


# ── get_event_evidence ──────────────────────────────────────


class TestGetEventEvidence:
    @pytest.mark.asyncio
    async def test_returns_evidence_list(self) -> None:
        """returns list of evidence links."""
        session = _mock_session()
        link1 = TimelineEventEvidence(
            event_id=UUID(_EVENT_ID),
            relationship="supports",
            linked_by=UUID(_USER_ID),
        )
        link2 = TimelineEventEvidence(
            event_id=UUID(_EVENT_ID),
            relationship="contradicts",
            linked_by=UUID(_USER_ID),
        )
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = [link1, link2]
        mock_result.scalars.return_value = mock_scalars
        session.execute.return_value = mock_result

        evidence = await get_event_evidence(session, _EVENT_ID)
        assert len(evidence) == 2

    @pytest.mark.asyncio
    async def test_returns_empty_list(self) -> None:
        """returns empty list when no evidence linked."""
        session = _mock_session()
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = []
        mock_result.scalars.return_value = mock_scalars
        session.execute.return_value = mock_result

        evidence = await get_event_evidence(session, _EVENT_ID)
        assert evidence == []


# ── get_timeline ────────────────────────────────────────────


class TestGetTimeline:
    @pytest.mark.asyncio
    async def test_attaches_evidence_to_each_event(self) -> None:
        """each event gets an evidence attribute."""
        session = _mock_session()
        event = TimelineEvent(
            case_id=UUID(_CASE_ID),
            title="E",
            event_time_start=_NOW,
            created_by=UUID(_USER_ID),
        )
        event.id = uuid4()

        link = TimelineEventEvidence(
            event_id=event.id,
            relationship="supports",
            linked_by=UUID(_USER_ID),
        )

        # list_events: count + data
        count_result = MagicMock()
        count_result.scalar_one.return_value = 1
        row = MagicMock()
        row.__getitem__ = lambda self, i: [event, 1, 1, 0][i]
        data_result = MagicMock()
        data_result.all.return_value = [row]

        # get_event_evidence for single event
        ev_result = MagicMock()
        ev_scalars = MagicMock()
        ev_scalars.all.return_value = [link]
        ev_result.scalars.return_value = ev_scalars

        session.execute.side_effect = [
            count_result,
            data_result,
            ev_result,
        ]

        events = await get_timeline(session, _CASE_ID)
        assert len(events) == 1
        assert events[0].evidence == [link]


# ── get_timeline batch fetch ───────────────────────────────


class TestGetTimelineBatchFetch:
    @pytest.mark.asyncio
    async def test_empty_events_returns_empty(self) -> None:
        """no events means no evidence query needed."""
        session = _mock_session()
        # list_events: count=0, empty rows
        count_result = MagicMock()
        count_result.scalar_one.return_value = 0
        data_result = MagicMock()
        data_result.all.return_value = []
        session.execute.side_effect = [count_result, data_result]

        result = await get_timeline(session, _CASE_ID)
        assert result == []
        # only 2 execute calls (count + data for list_events)
        assert session.execute.await_count == 2

    @pytest.mark.asyncio
    async def test_batch_fetches_evidence(self) -> None:
        """evidence fetched in single query, not per-event."""
        session = _mock_session()
        events = []
        rows = []
        for i in range(3):
            e = TimelineEvent(
                case_id=UUID(_CASE_ID),
                title=f"E{i}",
                event_time_start=_NOW,
                created_by=UUID(_USER_ID),
            )
            e.id = uuid4()
            events.append(e)
            row = MagicMock()
            vals = [e, 0, 0, 0]
            row.__getitem__ = (
                lambda self, i, v=vals: v[i]
            )
            rows.append(row)

        # evidence for event 0 and event 2 only
        ev0 = TimelineEventEvidence(
            event_id=events[0].id,
            relationship="supports",
            linked_by=UUID(_USER_ID),
        )
        ev2 = TimelineEventEvidence(
            event_id=events[2].id,
            relationship="contradicts",
            linked_by=UUID(_USER_ID),
        )

        count_result = MagicMock()
        count_result.scalar_one.return_value = 3
        data_result = MagicMock()
        data_result.all.return_value = rows

        # batch evidence query
        ev_result = MagicMock()
        ev_scalars = MagicMock()
        ev_scalars.all.return_value = [ev0, ev2]
        ev_result.scalars.return_value = ev_scalars

        session.execute.side_effect = [
            count_result,
            data_result,
            ev_result,
        ]

        result = await get_timeline(session, _CASE_ID)
        # exactly 3 execute calls: count, data, batch evidence
        assert session.execute.await_count == 3
        assert len(result) == 3

    @pytest.mark.asyncio
    async def test_evidence_grouped_by_event(self) -> None:
        """each event gets only its own evidence."""
        session = _mock_session()
        e1 = TimelineEvent(
            case_id=UUID(_CASE_ID),
            title="E1",
            event_time_start=_NOW,
            created_by=UUID(_USER_ID),
        )
        e1.id = uuid4()
        e2 = TimelineEvent(
            case_id=UUID(_CASE_ID),
            title="E2",
            event_time_start=_NOW,
            created_by=UUID(_USER_ID),
        )
        e2.id = uuid4()

        ev1 = TimelineEventEvidence(
            event_id=e1.id,
            relationship="supports",
            linked_by=UUID(_USER_ID),
        )
        ev2a = TimelineEventEvidence(
            event_id=e2.id,
            relationship="contradicts",
            linked_by=UUID(_USER_ID),
        )
        ev2b = TimelineEventEvidence(
            event_id=e2.id,
            relationship="context",
            linked_by=UUID(_USER_ID),
        )

        row1 = MagicMock()
        row1.__getitem__ = lambda self, i: [e1, 1, 1, 0][i]
        row2 = MagicMock()
        row2.__getitem__ = lambda self, i: [e2, 2, 0, 1][i]

        count_result = MagicMock()
        count_result.scalar_one.return_value = 2
        data_result = MagicMock()
        data_result.all.return_value = [row1, row2]

        ev_result = MagicMock()
        ev_scalars = MagicMock()
        ev_scalars.all.return_value = [ev1, ev2a, ev2b]
        ev_result.scalars.return_value = ev_scalars

        session.execute.side_effect = [
            count_result,
            data_result,
            ev_result,
        ]

        result = await get_timeline(session, _CASE_ID)
        assert result[0].evidence == [ev1]
        assert result[1].evidence == [ev2a, ev2b]
