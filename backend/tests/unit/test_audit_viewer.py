"""unit tests for loom.services.audit_viewer."""

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from loom.models.audit import AuditLogEntry
from loom.services.audit_viewer import (
    get_audit_stats,
    list_audit_entries,
)

_USER_ID = uuid4()
_NOW = datetime.now(tz=timezone.utc)


def _mock_session() -> AsyncMock:
    """build a mock async session."""
    s = AsyncMock()
    return s


def _make_audit_entry(
    action: str = "POST /api/v1/cases",
    resource_type: str = "cases",
    actor_id=_USER_ID,
    timestamp: datetime | None = None,
) -> AuditLogEntry:
    """create an audit log entry."""
    entry = AuditLogEntry(
        actor_id=actor_id,
        action=action,
        resource_type=resource_type,
        resource_id=uuid4(),
        timestamp=timestamp or _NOW,
    )
    entry.id = uuid4()
    return entry


# ── list_audit_entries ─────────────────────────────────────


class TestListAuditEntries:
    @pytest.mark.asyncio
    async def test_returns_entries_and_count(self) -> None:
        """should return paginated entries with total."""
        session = _mock_session()
        entries = [
            _make_audit_entry(),
            _make_audit_entry(),
        ]

        call_count = 0

        async def mock_execute(query):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                # count query
                r = MagicMock()
                r.scalar_one.return_value = 2
                return r
            else:
                # data query
                r = MagicMock()
                mock_scalars = MagicMock()
                mock_scalars.all.return_value = entries
                r.scalars.return_value = mock_scalars
                return r

        session.execute = mock_execute

        result, total = await list_audit_entries(session, skip=0, limit=20)

        assert total == 2
        assert len(result) == 2

    @pytest.mark.asyncio
    async def test_filter_by_actor(self) -> None:
        """filtering by actor_id should be applied."""
        session = _mock_session()
        entry = _make_audit_entry(actor_id=_USER_ID)

        call_count = 0

        async def mock_execute(query):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                r = MagicMock()
                r.scalar_one.return_value = 1
                return r
            else:
                r = MagicMock()
                mock_scalars = MagicMock()
                mock_scalars.all.return_value = [entry]
                r.scalars.return_value = mock_scalars
                return r

        session.execute = mock_execute

        result, total = await list_audit_entries(
            session, actor_id=_USER_ID, skip=0, limit=20
        )

        assert total == 1
        assert len(result) == 1

    @pytest.mark.asyncio
    async def test_filter_by_date_range(self) -> None:
        """date range filtering should be applied."""
        session = _mock_session()
        entry = _make_audit_entry(timestamp=_NOW)

        call_count = 0

        async def mock_execute(query):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                r = MagicMock()
                r.scalar_one.return_value = 1
                return r
            else:
                r = MagicMock()
                mock_scalars = MagicMock()
                mock_scalars.all.return_value = [entry]
                r.scalars.return_value = mock_scalars
                return r

        session.execute = mock_execute

        result, total = await list_audit_entries(
            session,
            date_from=_NOW - timedelta(hours=1),
            date_to=_NOW + timedelta(hours=1),
            skip=0,
            limit=20,
        )

        assert total == 1
        assert len(result) == 1

    @pytest.mark.asyncio
    async def test_filter_by_case_id(self) -> None:
        """case_id filtering uses action path matching."""
        session = _mock_session()
        case_id = str(uuid4())
        entry = _make_audit_entry(action=f"POST /api/v1/cases/{case_id}/assets")

        call_count = 0

        async def mock_execute(query):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                r = MagicMock()
                r.scalar_one.return_value = 1
                return r
            else:
                r = MagicMock()
                mock_scalars = MagicMock()
                mock_scalars.all.return_value = [entry]
                r.scalars.return_value = mock_scalars
                return r

        session.execute = mock_execute

        result, total = await list_audit_entries(
            session, case_id=case_id, skip=0, limit=20
        )

        assert total == 1

    @pytest.mark.asyncio
    async def test_empty_result(self) -> None:
        """should handle empty results."""
        session = _mock_session()

        call_count = 0

        async def mock_execute(query):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                r = MagicMock()
                r.scalar_one.return_value = 0
                return r
            else:
                r = MagicMock()
                mock_scalars = MagicMock()
                mock_scalars.all.return_value = []
                r.scalars.return_value = mock_scalars
                return r

        session.execute = mock_execute

        result, total = await list_audit_entries(session, skip=0, limit=20)

        assert total == 0
        assert len(result) == 0

    @pytest.mark.asyncio
    async def test_pagination(self) -> None:
        """skip and limit should be respected."""
        session = _mock_session()

        call_count = 0

        async def mock_execute(query):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                r = MagicMock()
                r.scalar_one.return_value = 50
                return r
            else:
                r = MagicMock()
                mock_scalars = MagicMock()
                mock_scalars.all.return_value = [
                    _make_audit_entry() for _ in range(10)
                ]
                r.scalars.return_value = mock_scalars
                return r

        session.execute = mock_execute

        result, total = await list_audit_entries(session, skip=20, limit=10)

        assert total == 50
        assert len(result) == 10


# ── get_audit_stats ────────────────────────────────────────


class TestGetAuditStats:
    @pytest.mark.asyncio
    async def test_returns_stats(self) -> None:
        """should return summary statistics."""
        session = _mock_session()

        call_count = 0

        async def mock_execute(query):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                # total count
                r = MagicMock()
                r.scalar_one.return_value = 42
                return r
            elif call_count == 2:
                # by action
                r = MagicMock()
                r.all.return_value = [
                    ("POST /api/v1/cases", 20),
                    ("PUT /api/v1/cases/x", 15),
                    ("DELETE /api/v1/cases/x", 7),
                ]
                return r
            elif call_count == 3:
                # by actor
                r = MagicMock()
                r.all.return_value = [
                    (_USER_ID, 30),
                ]
                return r
            else:
                # date range
                r = MagicMock()
                r.one.return_value = (
                    _NOW - timedelta(days=30),
                    _NOW,
                )
                return r

        session.execute = mock_execute

        stats = await get_audit_stats(session)

        assert stats.total_entries == 42
        assert len(stats.by_action) == 3
        assert len(stats.by_actor) == 1
        assert stats.earliest_entry is not None
        assert stats.latest_entry is not None

    @pytest.mark.asyncio
    async def test_stats_with_case_filter(self) -> None:
        """case_id filter should apply to all queries."""
        session = _mock_session()
        case_id = str(uuid4())

        call_count = 0

        async def mock_execute(query):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                r = MagicMock()
                r.scalar_one.return_value = 5
                return r
            elif call_count == 2:
                r = MagicMock()
                r.all.return_value = [
                    ("POST /api/v1/cases/" + case_id, 5),
                ]
                return r
            elif call_count == 3:
                r = MagicMock()
                r.all.return_value = [(_USER_ID, 5)]
                return r
            else:
                r = MagicMock()
                r.one.return_value = (_NOW, _NOW)
                return r

        session.execute = mock_execute

        stats = await get_audit_stats(session, case_id=case_id)

        assert stats.total_entries == 5

    @pytest.mark.asyncio
    async def test_empty_stats(self) -> None:
        """should handle empty audit log."""
        session = _mock_session()

        call_count = 0

        async def mock_execute(query):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                r = MagicMock()
                r.scalar_one.return_value = 0
                return r
            elif call_count in (2, 3):
                r = MagicMock()
                r.all.return_value = []
                return r
            else:
                r = MagicMock()
                r.one.return_value = (None, None)
                return r

        session.execute = mock_execute

        stats = await get_audit_stats(session)

        assert stats.total_entries == 0
        assert len(stats.by_action) == 0
        assert len(stats.by_actor) == 0
        assert stats.earliest_entry is None
        assert stats.latest_entry is None
