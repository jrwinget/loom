"""append-only policy tests for audit + custody models.

Exercises the portable ORM-level guards registered in
``loom.models._append_only``. Uses a sync sqlite session because
the ``before_update`` / ``before_delete`` hooks fire identically
regardless of the session flavor; sync keeps the test free of
the aiosqlite dependency. The Postgres trigger installed by
migration 011 is covered by CI's migration round-trip.
"""

from collections.abc import Iterator
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from loom.models._append_only import AppendOnlyViolationError
from loom.models.audit import AuditLogEntry
from loom.models.base import Base
from loom.models.chain_of_custody import ChainOfCustodyEntry


@pytest.fixture
def session() -> Iterator[Session]:
    engine = create_engine("sqlite://", future=True)
    # only the tables we're testing — Base.metadata.create_all
    # blows up on JSONB columns in other models that are
    # postgres-only.
    with engine.begin() as conn:
        Base.metadata.create_all(
            conn,
            tables=[
                AuditLogEntry.__table__,
                ChainOfCustodyEntry.__table__,
            ],
        )
    factory = sessionmaker(engine, expire_on_commit=False)
    with factory() as s:
        yield s
    engine.dispose()


def _make_audit() -> AuditLogEntry:
    return AuditLogEntry(
        id=uuid4(),
        actor_id=None,
        action="test.action",
        resource_type="test",
        resource_id=uuid4(),
        detail=None,
        ip_address=None,
        user_agent=None,
        timestamp=datetime.now(UTC),
    )


def _make_custody() -> ChainOfCustodyEntry:
    return ChainOfCustodyEntry(
        id=uuid4(),
        asset_id=uuid4(),
        action="ingest.hash-verified",
        actor_id=uuid4(),
        detail=None,
        ip_address=None,
        timestamp=datetime.now(UTC),
    )


def test_audit_insert_allowed(session: Session) -> None:
    entry = _make_audit()
    session.add(entry)
    session.commit()


def test_audit_update_rejected(session: Session) -> None:
    entry = _make_audit()
    session.add(entry)
    session.commit()

    entry.action = "tampered.action"
    with pytest.raises(
        AppendOnlyViolationError, match="audit_log is append-only"
    ):
        session.flush()


def test_audit_delete_rejected(session: Session) -> None:
    entry = _make_audit()
    session.add(entry)
    session.commit()

    session.delete(entry)
    with pytest.raises(
        AppendOnlyViolationError, match="audit_log is append-only"
    ):
        session.flush()


def test_custody_insert_allowed(session: Session) -> None:
    entry = _make_custody()
    session.add(entry)
    session.commit()


def test_custody_update_rejected(session: Session) -> None:
    entry = _make_custody()
    session.add(entry)
    session.commit()

    entry.action = "tampered.action"
    with pytest.raises(
        AppendOnlyViolationError,
        match="chain_of_custody_entries is append-only",
    ):
        session.flush()


def test_custody_delete_rejected(session: Session) -> None:
    entry = _make_custody()
    session.add(entry)
    session.commit()

    session.delete(entry)
    with pytest.raises(
        AppendOnlyViolationError,
        match="chain_of_custody_entries is append-only",
    ):
        session.flush()
