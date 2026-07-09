"""performance guardrails for the clustering read path.

the query-count test is the real regression guard: it proves
compute_absolute_times issues a constant number of queries
regardless of how many assets a case has (the old shape was
3 queries per asset). it runs in the default suite because it is
deterministic and fast.

the latency benchmark is opt-in (``-m perf``) and advisory: it
records p50/p95 to the ci step summary and fails only if the batched
path regresses past a generous ceiling, so normal wall-clock jitter
never breaks a build.
"""

from __future__ import annotations

import os
import time
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from sqlalchemy import event
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from loom.models.annotation import Annotation
from loom.models.asset import Asset
from loom.models.base import Base
from loom.models.case import Case
from loom.models.ocr import OcrRegion
from loom.models.transcript import TranscriptSegment
from loom.services.clustering import compute_absolute_times

_ACTOR = uuid4()


async def _seed(session: AsyncSession, *, assets: int) -> str:
    """seed a case with ``assets`` capture-timed assets, each with a
    transcript segment, an ocr region, and a timed annotation."""
    case = Case(name="Perf Case", created_by=_ACTOR, status="active")
    session.add(case)
    await session.flush()
    base = datetime(2026, 1, 1, tzinfo=UTC)
    for i in range(assets):
        asset = Asset(
            case_id=case.id,
            original_filename=f"clip-{i}.mp4",
            storage_key=f"{case.id}/{uuid4()}/clip-{i}.mp4",
            media_type="video",
            mime_type="video/mp4",
            file_size_bytes=1,
            sha256_hash="a" * 64,
            sha512_hash="b" * 128,
            uploaded_by=_ACTOR,
            upload_status="complete",
            processing_status="complete",
            capture_time=base,
        )
        session.add(asset)
        await session.flush()
        session.add(
            TranscriptSegment(
                asset_id=asset.id,
                start_time=1.0,
                end_time=2.0,
                text="hello",
            )
        )
        session.add(OcrRegion(asset_id=asset.id, timestamp=1.5, text="sign"))
        session.add(
            Annotation(
                asset_id=asset.id,
                case_id=case.id,
                type="observation",
                content="note",
                time_start=1.0,
                created_by=_ACTOR,
            )
        )
    await session.flush()
    return str(case.id)


class _SelectCounter:
    def __init__(self) -> None:
        self.count = 0

    def __call__(self, conn, cursor, statement, *args: object) -> None:
        if statement.lstrip().upper().startswith("SELECT"):
            self.count += 1


async def _session_and_counter() -> tuple[AsyncSession, _SelectCounter, object]:
    engine = create_async_engine("sqlite+aiosqlite://")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    counter = _SelectCounter()
    event.listen(engine.sync_engine, "before_cursor_execute", counter)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    return factory(), counter, engine


@pytest.mark.asyncio
async def test_query_count_is_constant_regardless_of_asset_count() -> None:
    # the guard against the 3-per-asset n+1: the query count for a
    # 5-asset case and a 40-asset case must be identical
    counts: dict[int, int] = {}
    for n in (5, 40):
        session, counter, engine = await _session_and_counter()
        try:
            case_id = await _seed(session, assets=n)
            counter.count = 0
            items = await compute_absolute_times(session, case_id)
            counts[n] = counter.count
            # 3 content items per asset (transcript, ocr, annotation)
            assert len(items) == n * 3
        finally:
            await engine.dispose()

    assert counts[5] == counts[40], (
        f"query count scales with assets: {counts} — the n+1 is back"
    )
    # 1 assets query + 3 content queries
    assert counts[40] <= 4, f"expected <=4 queries, got {counts[40]}"


@pytest.mark.perf
@pytest.mark.asyncio
async def test_compute_absolute_times_latency() -> None:
    session, _counter, engine = await _session_and_counter()
    try:
        case_id = await _seed(session, assets=500)
        samples: list[float] = []
        for _ in range(20):
            start = time.perf_counter()
            await compute_absolute_times(session, case_id)
            samples.append((time.perf_counter() - start) * 1000)
    finally:
        await engine.dispose()

    samples.sort()
    p50 = samples[len(samples) // 2]
    p95 = samples[int(len(samples) * 0.95)]

    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a", encoding="utf-8") as fh:
            fh.write(
                f"### compute_absolute_times (500 assets, 1500 items)\n"
                f"- p50: {p50:.1f} ms\n- p95: {p95:.1f} ms\n"
            )

    # generous ceiling — advisory, guards a gross regression only
    assert p95 < 2000, f"p95 {p95:.1f}ms exceeds the 2s ceiling"
