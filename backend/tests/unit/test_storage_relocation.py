"""unit tests for the lite-profile storage relocation service.

covers the pure logic (advisories, path probes, hashing) plus an
end-to-end relocation on a temp dir backed by an in-memory sqlite
db. chain-of-custody inserts are asserted because relocation is
an evidentiary action — a move without custody is a tamper gap.
"""

from __future__ import annotations

import asyncio
import hashlib
from collections.abc import Iterator
from pathlib import Path
from types import TracebackType
from typing import Any
from uuid import UUID, uuid4

import pytest
from sqlalchemy import Engine, create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from loom.models.base import Base
from loom.models.chain_of_custody import ChainOfCustodyEntry
from loom.services.storage_backends import (
    ORIGINALS_BUCKET,
    LocalStorageBackend,
)
from loom.services.storage_relocation import (
    RELOCATION_REGISTRY,
    _hash_file,
    compute_advisory,
    get_storage_usage,
    probe_path_writable,
    start_relocation,
)


@pytest.fixture(autouse=True)
def _clear_registry() -> Iterator[None]:
    """relocation registry is module-level; scrub between tests."""
    RELOCATION_REGISTRY.clear()
    yield
    RELOCATION_REGISTRY.clear()


# ---------------------------------------------------------------------
# compute_advisory
# ---------------------------------------------------------------------


class TestComputeAdvisory:
    def test_proceeds_when_batch_fits_comfortably(self) -> None:
        advisory, reason = compute_advisory(
            free_bytes=100 * 1024**3,
            total_bytes=1024 * 1024**3,
            estimated_batch_size=1 * 1024**3,
            on_system_drive=False,
        )
        assert advisory == "proceed"
        assert reason is None

    def test_warns_when_batch_exceeds_half_free(self) -> None:
        advisory, reason = compute_advisory(
            free_bytes=10 * 1024**3,
            total_bytes=100 * 1024**3,
            # 6gib batch vs 10gib free -> exceeds 50% ratio
            estimated_batch_size=6 * 1024**3,
            on_system_drive=False,
        )
        assert advisory == "warning"
        assert reason is not None
        assert "half" in reason.lower()

    def test_warns_on_small_system_drive(self) -> None:
        advisory, reason = compute_advisory(
            free_bytes=400 * 1024**3,
            total_bytes=256 * 1024**3,  # <=512gib cutoff
            # 11gib batch > 10gib small-disk threshold
            estimated_batch_size=11 * 1024**3,
            on_system_drive=True,
        )
        assert advisory == "warning"
        assert reason is not None
        assert "system drive" in reason.lower()

    def test_warns_on_large_system_drive(self) -> None:
        advisory, reason = compute_advisory(
            free_bytes=900 * 1024**3,
            # >512gib so large-drive threshold (50gib) applies
            total_bytes=2 * 1024 * 1024**3,
            estimated_batch_size=60 * 1024**3,
            on_system_drive=True,
        )
        assert advisory == "warning"
        assert reason is not None

    def test_system_drive_small_batch_still_proceeds(self) -> None:
        advisory, reason = compute_advisory(
            free_bytes=400 * 1024**3,
            total_bytes=256 * 1024**3,
            # 1gib batch well under the 10gib small-disk threshold
            estimated_batch_size=1 * 1024**3,
            on_system_drive=True,
        )
        assert advisory == "proceed"
        assert reason is None


# ---------------------------------------------------------------------
# probe_path_writable
# ---------------------------------------------------------------------


class TestProbePathWritable:
    def test_writable_tempdir(self, tmp_path: Path) -> None:
        ok, reason = probe_path_writable(tmp_path)
        assert ok is True
        assert reason is None

    def test_creates_missing_parent(self, tmp_path: Path) -> None:
        target = tmp_path / "nested" / "child"
        ok, reason = probe_path_writable(target)
        assert ok is True
        assert reason is None
        assert target.is_dir()

    @pytest.mark.parametrize(
        "token",
        ["icloud", "OneDrive", "Google Drive", "Dropbox"],
    )
    def test_rejects_cloud_sync_paths(self, tmp_path: Path, token: str) -> None:
        fake = tmp_path / token / "loom-data"
        ok, reason = probe_path_writable(fake)
        assert ok is False
        assert reason is not None
        assert "cloud-sync" in reason.lower()


# ---------------------------------------------------------------------
# _hash_file
# ---------------------------------------------------------------------


class TestHashFile:
    def test_matches_stdlib(self, tmp_path: Path) -> None:
        payload = b"loom-relocation-test" * 4096
        src = tmp_path / "payload.bin"
        src.write_bytes(payload)
        assert _hash_file(src) == hashlib.sha256(payload).hexdigest()


# ---------------------------------------------------------------------
# get_storage_usage
# ---------------------------------------------------------------------


class TestGetStorageUsage:
    def test_reports_nonzero_totals(self, tmp_path: Path) -> None:
        # populate a bucket so the breakdown has something to count
        backend = LocalStorageBackend(tmp_path, signing_secret="s")
        backend.ensure_buckets()
        backend.upload_bytes(
            ORIGINALS_BUCKET,
            "case/asset/file.bin",
            b"x" * 1024,
            "application/octet-stream",
        )
        usage = get_storage_usage(tmp_path)
        assert usage["data_dir"] == str(tmp_path.resolve())
        assert int(usage["total_bytes"]) > 0
        assert int(usage["originals_bytes"]) >= 1024
        assert int(usage["db_bytes"]) == 0
        assert int(usage["logs_bytes"]) == 0


# ---------------------------------------------------------------------
# end-to-end relocation
# ---------------------------------------------------------------------


class _AsyncSessionAdapter:
    """minimal async facade over a sync sqlalchemy Session.

    the relocation code only calls ``add``, ``commit``, and the
    ``async with`` protocol on its sessions — we don't need a real
    AsyncSession (and can't easily use one here because aiosqlite
    isn't in the backend deps). the test-only adapter keeps the
    production code honest about what it actually requires.
    """

    def __init__(self, factory: sessionmaker[Session]) -> None:
        self._factory = factory
        self._session: Session | None = None

    async def __aenter__(self) -> _AsyncSessionAdapter:
        self._session = self._factory()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        assert self._session is not None
        self._session.close()
        self._session = None

    def add(self, obj: Any) -> None:
        assert self._session is not None
        self._session.add(obj)

    async def commit(self) -> None:
        assert self._session is not None
        self._session.commit()


@pytest.fixture
def sync_engine() -> Iterator[Engine]:
    """in-memory sqlite engine with only the custody table created.

    we build just this one table because the rest of the ORM uses
    postgres-only JSONB columns that can't materialize on sqlite.
    """
    engine = create_engine(
        "sqlite:///file::memory:?cache=shared&uri=true",
        future=True,
    )
    with engine.begin() as conn:
        Base.metadata.create_all(
            conn,
            tables=[ChainOfCustodyEntry.__table__],
        )
    yield engine
    engine.dispose()


@pytest.fixture
def async_session_factory(
    sync_engine: Engine,
) -> Any:
    """return a zero-arg callable yielding the adapter per call."""
    factory = sessionmaker(sync_engine, expire_on_commit=False)

    def _factory() -> _AsyncSessionAdapter:
        return _AsyncSessionAdapter(factory)

    return _factory


async def _wait_for_job(job_id: str, timeout: float = 5.0) -> None:
    """poll until the background relocation task drops out of running."""
    loop_deadline = asyncio.get_running_loop().time() + timeout
    while asyncio.get_running_loop().time() < loop_deadline:
        job = RELOCATION_REGISTRY[job_id]
        if job.status != "running":
            return
        await asyncio.sleep(0.02)
    raise AssertionError(f"relocation {job_id} did not finish in time")


@pytest.mark.asyncio
async def test_end_to_end_relocation_copies_and_logs_custody(
    tmp_path: Path,
    sync_engine: Engine,
    async_session_factory: Any,
) -> None:
    src_dir = tmp_path / "src"
    dst_dir = tmp_path / "dst"
    src_dir.mkdir()

    # lay down two assets via the real lite backend so the path
    # layout (buckets/loom-originals/<case>/<asset>/<file>) matches
    # what relocation walks in production.
    backend = LocalStorageBackend(src_dir, signing_secret="unit-test")
    backend.ensure_buckets()
    case_id = str(uuid4())
    asset_a = str(uuid4())
    asset_b = str(uuid4())
    payload_a = b"asset-a-bytes" * 256
    payload_b = b"asset-b-bytes" * 1024
    backend.upload_bytes(
        ORIGINALS_BUCKET,
        f"{case_id}/{asset_a}/a.bin",
        payload_a,
        "application/octet-stream",
    )
    backend.upload_bytes(
        ORIGINALS_BUCKET,
        f"{case_id}/{asset_b}/b.bin",
        payload_b,
        "application/octet-stream",
    )

    user_id = uuid4()
    job = start_relocation(
        async_session_factory,
        src_dir,
        dst_dir,
        user_id,
    )
    assert job.assets_total == 2
    assert job.bytes_total == len(payload_a) + len(payload_b)

    await _wait_for_job(job.job_id)

    job = RELOCATION_REGISTRY[job.job_id]
    assert job.status == "completed", job.error
    assert job.assets_copied == 2
    assert job.bytes_copied == len(payload_a) + len(payload_b)

    # both files must exist at destination with matching content.
    dst_a = dst_dir / "buckets" / ORIGINALS_BUCKET / case_id / asset_a / "a.bin"
    dst_b = dst_dir / "buckets" / ORIGINALS_BUCKET / case_id / asset_b / "b.bin"
    assert dst_a.read_bytes() == payload_a
    assert dst_b.read_bytes() == payload_b

    # one custody entry per evidentiary file, keyed on the asset id
    # extracted from the storage key.
    with Session(sync_engine) as session:
        entries = list(session.execute(select(ChainOfCustodyEntry)).scalars())
    assert len(entries) == 2
    actions = {e.action for e in entries}
    assert actions == {"data_dir_relocated"}
    asset_ids = {e.asset_id for e in entries}
    assert asset_ids == {UUID(asset_a), UUID(asset_b)}
    for entry in entries:
        assert entry.detail is not None
        assert entry.detail["from"] == str(src_dir.resolve())
        assert entry.detail["to"] == str(dst_dir.resolve())
        assert "verified_hash" in entry.detail


@pytest.mark.asyncio
async def test_start_relocation_rejects_nested_target(
    tmp_path: Path,
    async_session_factory: Any,
) -> None:
    src = tmp_path / "data"
    src.mkdir()
    # dst inside src is a circular move — must be rejected.
    dst = src / "child"

    with pytest.raises(ValueError, match="inside"):
        start_relocation(async_session_factory, src, dst, uuid4())


@pytest.mark.asyncio
async def test_start_relocation_rejects_concurrent_jobs(
    tmp_path: Path,
    async_session_factory: Any,
) -> None:
    src = tmp_path / "src"
    src.mkdir()
    dst1 = tmp_path / "dst1"
    dst2 = tmp_path / "dst2"

    # first call starts a job — registry now holds one "running".
    first = start_relocation(async_session_factory, src, dst1, uuid4())
    try:
        with pytest.raises(ValueError, match="already in progress"):
            start_relocation(async_session_factory, src, dst2, uuid4())
    finally:
        # let the background task drain so asyncio doesn't warn
        # about un-awaited tasks at teardown.
        await _wait_for_job(first.job_id)
