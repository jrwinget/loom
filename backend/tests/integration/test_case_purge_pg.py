"""postgres coverage: case purge vs the append-only custody trigger.

migration 011 installs BEFORE UPDATE/DELETE triggers on audit_log
and chain_of_custody_entries, and postgres row triggers also fire
for FK-cascade deletes — so purge_case's cascade (cases → assets →
chain_of_custody_entries) aborted on the server profile while the
lite profile (create_all installs no triggers) purged fine.
migration 022 gates the trigger function on the transaction-local
``loom.allow_purge`` flag that purge_case sets, scoped so custody
UPDATEs and audit_log rows stay rejected even with the flag on.

runs inside the CI ``test-migrations`` job against its migrated
postgres service (the job runs ``alembic upgrade head`` before
pytest). skipped everywhere else (the default test job runs on
sqlite, where the ORM listeners are the enforcement layer).
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy import func, select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from loom.models.asset import Asset
from loom.models.audit import AuditLogEntry
from loom.models.case import Case
from loom.models.chain_of_custody import ChainOfCustodyEntry
from loom.models.user import User
from loom.services.case import purge_case

_DB_URL = os.environ.get("LOOM_DATABASE_URL", "")

pytestmark = [
    pytest.mark.skipif(
        not _DB_URL.startswith("postgresql"),
        reason="append-only triggers exist only on the migrated postgres db",
    ),
    pytest.mark.asyncio,
]


class _RecordingStorage:
    """purge_case only calls delete_object; record the calls."""

    def __init__(self) -> None:
        self.deleted: list[tuple[str, str]] = []

    def delete_object(self, bucket: str, key: str) -> None:
        self.deleted.append((bucket, key))


@pytest_asyncio.fixture
async def engine() -> AsyncIterator[AsyncEngine]:
    engine = create_async_engine(_DB_URL)
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture
async def session(engine: AsyncEngine) -> AsyncIterator[AsyncSession]:
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as session:
        yield session


async def _seed_case(
    session: AsyncSession,
) -> tuple[User, Case, Asset]:
    """commit a user, closed case, one asset, and two custody rows.

    unique email/storage key so reruns against a persistent dev db
    never collide; custody and audit rows are append-only and simply
    accumulate there.
    """
    user = User(
        email=f"purge-{uuid4()}@example.org",
        display_name="Purge Tester",
        role="admin",
        password_hash="x",
    )
    session.add(user)
    await session.flush()

    case = Case(
        name="Operation Nightfall",
        description="d",
        status="closed",
        created_by=user.id,
    )
    session.add(case)
    await session.flush()

    asset = Asset(
        case_id=case.id,
        original_filename="evidence.pdf",
        storage_key=f"originals/{uuid4()}",
        media_type="document",
        mime_type="application/pdf",
        file_size_bytes=42,
        sha256_hash="a" * 64,
        sha512_hash="b" * 128,
        upload_status="complete",
        uploaded_by=user.id,
    )
    session.add(asset)
    await session.flush()

    session.add_all(
        ChainOfCustodyEntry(
            asset_id=asset.id,
            action=action,
            actor_id=user.id,
        )
        for action in ("ingest_started", "ingest_completed")
    )
    await session.commit()
    return user, case, asset


async def _custody_count(session: AsyncSession, asset_id: object) -> int:
    result = await session.execute(
        select(func.count())
        .select_from(ChainOfCustodyEntry)
        .where(ChainOfCustodyEntry.asset_id == asset_id)
    )
    return result.scalar_one()


async def test_purge_cascades_past_append_only_trigger(
    session: AsyncSession,
) -> None:
    user, case, asset = await _seed_case(session)
    case_id, asset_id, storage_key = case.id, asset.id, asset.storage_key
    assert await _custody_count(session, asset_id) == 2

    storage = _RecordingStorage()
    await purge_case(
        session,
        case,
        reason="retention window elapsed",
        actor_id=str(user.id),
        storage=storage,
    )

    case_left = await session.execute(select(Case).where(Case.id == case_id))
    assert case_left.scalar_one_or_none() is None
    assets_left = await session.execute(
        select(Asset).where(Asset.case_id == case_id)
    )
    assert assets_left.scalars().first() is None
    assert await _custody_count(session, asset_id) == 0

    tomb = await session.execute(
        select(AuditLogEntry).where(
            AuditLogEntry.action == "case_purged",
            AuditLogEntry.resource_id == case_id,
        )
    )
    entry = tomb.scalar_one()
    assert entry.detail["title"] == "Operation Nightfall"
    assert entry.detail["reason"] == "retention window elapsed"
    assert entry.detail["asset_count"] == 1
    assert entry.detail["assets"] == [
        {
            "id": str(asset_id),
            "original_filename": "evidence.pdf",
            "sha256": "a" * 64,
        }
    ]
    assert storage.deleted == [("loom-originals", storage_key)]


async def test_direct_custody_mutations_still_rejected(
    engine: AsyncEngine,
    session: AsyncSession,
) -> None:
    _user, _case, asset = await _seed_case(session)

    async with engine.connect() as conn:
        with pytest.raises(DBAPIError, match="append-only"):
            await conn.execute(
                text(
                    "DELETE FROM chain_of_custody_entries WHERE asset_id = :aid"
                ),
                {"aid": asset.id},
            )
        await conn.rollback()

        with pytest.raises(DBAPIError, match="append-only"):
            await conn.execute(
                text(
                    "UPDATE chain_of_custody_entries SET action = 'tampered'"
                    " WHERE asset_id = :aid"
                ),
                {"aid": asset.id},
            )
        await conn.rollback()

    assert await _custody_count(session, asset.id) == 2


async def test_purge_flag_never_unlocks_audit_log_or_custody_updates(
    engine: AsyncEngine,
    session: AsyncSession,
) -> None:
    user, _case, asset = await _seed_case(session)
    session.add(
        AuditLogEntry(
            actor_id=user.id,
            action="login",
            resource_type="auth",
        )
    )
    await session.commit()

    async with engine.connect() as conn:
        # autobegin puts SET LOCAL and the mutation in one transaction,
        # exactly the shape a hostile caller inside a purge would use
        await conn.execute(text("SET LOCAL loom.allow_purge = 'on'"))
        with pytest.raises(DBAPIError, match="append-only"):
            await conn.execute(
                text("DELETE FROM audit_log WHERE actor_id = :uid"),
                {"uid": user.id},
            )
        await conn.rollback()

        await conn.execute(text("SET LOCAL loom.allow_purge = 'on'"))
        with pytest.raises(DBAPIError, match="append-only"):
            await conn.execute(
                text(
                    "UPDATE chain_of_custody_entries SET action = 'tampered'"
                    " WHERE asset_id = :aid"
                ),
                {"aid": asset.id},
            )
        await conn.rollback()
