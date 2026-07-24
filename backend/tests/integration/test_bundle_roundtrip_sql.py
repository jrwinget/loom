"""portable bundle round-trip: export a case, import it into a fresh
one, and assert the evidence survives byte-for-byte with provenance
recorded. this is the contract the whole feature exists to keep."""

from __future__ import annotations

import hashlib
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from loom.models.annotation import Annotation
from loom.models.asset import Asset
from loom.models.base import Base
from loom.models.case import Case
from loom.models.chain_of_custody import ChainOfCustodyEntry
from loom.models.timeline import TimelineEvent
from loom.services.bundle_import import (
    _recreate_events,
    recreate_case_contents,
)
from loom.services.portable_bundle import build_portable_bundle, verify_bundle
from loom.services.storage_backends import ORIGINALS_BUCKET
from loom.services.storage_backends.local import LocalStorageBackend

_PAYLOAD = b"observer footage bytes, imported verbatim\n"


@pytest.fixture
async def session() -> AsyncSession:
    engine = create_async_engine("sqlite+aiosqlite://")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as s:
        yield s
    await engine.dispose()


def _storage(tmp_path: Path) -> LocalStorageBackend:
    return LocalStorageBackend(tmp_path, signing_secret="x" * 32)


async def _seed_source(
    session: AsyncSession, storage: LocalStorageBackend
) -> str:
    actor = uuid4()
    case = Case(name="Source Case", created_by=actor, status="active")
    session.add(case)
    await session.flush()

    sha = hashlib.sha256(_PAYLOAD).hexdigest()
    asset = Asset(
        case_id=case.id,
        original_filename="clip.txt",
        storage_key=f"{case.id}/{uuid4()}/clip.txt",
        media_type="document",
        mime_type="text/plain",
        file_size_bytes=len(_PAYLOAD),
        sha256_hash=sha,
        sha512_hash=hashlib.sha512(_PAYLOAD).hexdigest(),
        uploaded_by=actor,
        upload_status="complete",
        processing_status="complete",
    )
    session.add(asset)
    await session.flush()
    storage.upload_bytes(
        ORIGINALS_BUCKET, asset.storage_key, _PAYLOAD, "text/plain"
    )
    session.add(
        ChainOfCustodyEntry(
            asset_id=asset.id,
            action="upload",
            actor_id=actor,
            detail={"action": "file_uploaded"},
        )
    )
    session.add(
        TimelineEvent(
            case_id=case.id,
            title="A thing happened",
            event_time_start=__import__("datetime").datetime(2026, 7, 1),
            created_by=actor,
        )
    )
    session.add(
        Annotation(
            case_id=case.id,
            asset_id=asset.id,
            type="observation",
            content="note",
            created_by=actor,
        )
    )
    await session.flush()
    return str(case.id)


@pytest.mark.parametrize(
    "foreign_status",
    ["proposed", "accepted", "rejected", "archived", "garbage"],
)
async def test_import_clamps_unknown_event_status(
    session: AsyncSession, foreign_status: str
) -> None:
    """a foreign bundle's event status must never violate the model
    check constraint.

    bundles from other deploys (or hand-edited ones) carry whatever
    status string their writer produced; older postgres schemas even
    allowed 'archived'. importing one of those used to raise an
    IntegrityError at flush and abort the whole import.
    """
    importer = uuid4()
    case = Case(name="Imported", created_by=importer, status="closed")
    session.add(case)
    await session.flush()

    events_doc = [
        {
            "source_id": "e1",
            "title": "A thing happened",
            "event_time_start": "2026-07-01T00:00:00",
            "status": foreign_status,
        }
    ]
    event_map = await _recreate_events(session, case, events_doc, importer)

    event = await session.get(TimelineEvent, event_map["e1"])
    assert event is not None
    assert event.status == "draft"


@pytest.mark.parametrize("known_status", ["draft", "confirmed", "disputed"])
async def test_import_preserves_known_event_status(
    session: AsyncSession, known_status: str
) -> None:
    importer = uuid4()
    case = Case(name="Imported", created_by=importer, status="closed")
    session.add(case)
    await session.flush()

    events_doc = [
        {
            "source_id": "e1",
            "title": "A thing happened",
            "event_time_start": "2026-07-01T00:00:00",
            "status": known_status,
        }
    ]
    event_map = await _recreate_events(session, case, events_doc, importer)

    event = await session.get(TimelineEvent, event_map["e1"])
    assert event is not None
    assert event.status == known_status


async def test_export_import_preserves_evidence(
    session: AsyncSession, tmp_path: Path
) -> None:
    storage = _storage(tmp_path)
    source_case_id = await _seed_source(session, storage)

    bundle = tmp_path / "bundle.zip"
    bundle_sha = await build_portable_bundle(
        session, source_case_id, storage, bundle
    )

    # verification is the precondition the importer relies on
    status = verify_bundle(bundle, trusted_keys_pem=[])
    assert status.state == "unsigned"

    importer = uuid4()
    target = Case(
        name="Imported",
        created_by=importer,
        status="closed",
        source_bundle_sha256=bundle_sha,
    )
    session.add(target)
    await session.flush()

    counts = await recreate_case_contents(
        session,
        target,
        bundle,
        storage,
        importer_id=str(importer),
        signature=status,
        bundle_sha256=bundle_sha,
        source_deploy="peer",
    )
    await session.flush()

    assert counts == {"assets": 1, "events": 1, "annotations": 1}

    # the imported asset is a NEW row (new id, new key) but the same
    # bytes and hash as the source
    imported = list(
        (
            await session.scalars(
                select(Asset).where(Asset.case_id == target.id)
            )
        ).all()
    )
    assert len(imported) == 1
    new_asset = imported[0]
    assert new_asset.sha256_hash == hashlib.sha256(_PAYLOAD).hexdigest()
    assert new_asset.uploaded_by == importer
    assert str(target.id) in new_asset.storage_key

    # the stored original round-trips byte-for-byte
    _size, stream = storage.get_object_stream(
        ORIGINALS_BUCKET, new_asset.storage_key
    )
    assert b"".join(stream) == _PAYLOAD

    # custody: an imported entry, first in the chain, carrying the
    # source deploy's trail and the bundle provenance
    custody = list(
        (
            await session.scalars(
                select(ChainOfCustodyEntry).where(
                    ChainOfCustodyEntry.asset_id == new_asset.id
                )
            )
        ).all()
    )
    assert len(custody) == 1
    entry = custody[0]
    assert entry.action == "imported"
    assert entry.detail["bundle_sha256"] == bundle_sha
    assert entry.detail["source_deploy"] == "peer"
    assert entry.detail["signature_status"] == "unsigned"
    # the source chain travels embedded, not replayed as local rows
    assert entry.detail["source_custody_chain"][0]["action"] == "upload"
