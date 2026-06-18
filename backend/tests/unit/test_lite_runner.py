"""unit tests for the in-process lite workflow runner.

activities are replaced with plain async stubs so the runner is
exercised without temporal, a database, or storage.
"""

from unittest.mock import AsyncMock, patch

import pytest

from loom.workflows import lite_runner
from loom.workflows.sequences import Step, WorkflowSpec


def _spec(*steps: Step, asset_status_arg: int | None = None) -> WorkflowSpec:
    return WorkflowSpec("test", steps, asset_status_arg=asset_status_arg)


async def test_runs_steps_in_order() -> None:
    log: list[str] = []

    async def a(asset_id: str) -> None:
        log.append("a")

    async def b(asset_id: str) -> None:
        log.append("b")

    spec = _spec(
        Step(a, lambda args, r: [args[0]], timeout_s=1),
        Step(b, lambda args, r: [args[0]], timeout_s=1),
    )
    await lite_runner.run_sequence(spec, ["asset-1"])
    assert log == ["a", "b"]


async def test_threads_prior_results() -> None:
    seen: dict = {}

    async def first(asset_id: str) -> str:
        return "audio.wav"

    async def second(asset_id: str, audio_path: str) -> None:
        seen["audio"] = audio_path

    spec = _spec(
        Step(first, lambda args, r: [args[0]], timeout_s=1, result_key="audio"),
        Step(
            second,
            lambda args, r: [args[0], r["audio"]],
            timeout_s=1,
        ),
    )
    await lite_runner.run_sequence(spec, ["asset-1"])
    assert seen["audio"] == "audio.wav"


async def test_retries_then_succeeds() -> None:
    calls = {"n": 0}
    downstream: list[str] = []

    async def flaky(asset_id: str) -> None:
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("transient")

    async def after(asset_id: str) -> None:
        downstream.append("ran")

    spec = _spec(
        Step(flaky, lambda args, r: [args[0]], timeout_s=1, max_attempts=2),
        Step(after, lambda args, r: [args[0]], timeout_s=1),
    )
    await lite_runner.run_sequence(spec, ["asset-1"])
    assert calls["n"] == 2
    assert downstream == ["ran"]


async def test_no_explicit_retry_runs_once_then_raises() -> None:
    calls = {"n": 0}

    async def always_fail(asset_id: str) -> None:
        calls["n"] += 1
        raise RuntimeError("boom")

    spec = _spec(Step(always_fail, lambda args, r: [args[0]], timeout_s=1))
    with pytest.raises(RuntimeError, match="boom"):
        await lite_runner.run_sequence(spec, ["asset-1"])
    assert calls["n"] == 1


async def test_sets_processing_then_complete_path() -> None:
    async def noop(asset_id: str) -> None:
        return None

    spec = _spec(
        Step(noop, lambda args, r: [args[0]], timeout_s=1),
        asset_status_arg=0,
    )
    with patch.object(
        lite_runner, "_set_asset_status", new_callable=AsyncMock
    ) as set_status:
        await lite_runner.run_sequence(spec, ["asset-1"])
    # marks processing on entry; completion is the activity's job, so
    # no explicit "complete"/"failed" call on the happy path.
    set_status.assert_awaited_once_with("asset-1", "processing")


async def test_marks_failed_and_reraises_on_error() -> None:
    async def boom(asset_id: str) -> None:
        raise RuntimeError("down")

    spec = _spec(
        Step(boom, lambda args, r: [args[0]], timeout_s=1),
        asset_status_arg=0,
    )
    with (
        patch.object(
            lite_runner, "_set_asset_status", new_callable=AsyncMock
        ) as set_status,
        pytest.raises(RuntimeError, match="down"),
    ):
        await lite_runner.run_sequence(spec, ["asset-1"])
    statuses = [c.args[1] for c in set_status.await_args_list]
    assert statuses == ["processing", "failed"]
