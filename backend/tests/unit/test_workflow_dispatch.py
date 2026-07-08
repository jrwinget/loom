"""unit tests for the profile-aware workflow dispatch gateway."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from loom.services.engines import EngineUnavailableError
from loom.workflows import dispatch
from loom.workflows.sequences import INGEST

_LITE = SimpleNamespace(is_lite=True, temporal_host="unused")
_SERVER = SimpleNamespace(is_lite=False, temporal_host="localhost:7233")


@pytest.fixture(autouse=True)
def _clear_state():
    dispatch._BG_TASKS.clear()
    dispatch._LITE_STATUS.clear()
    yield
    dispatch._BG_TASKS.clear()
    dispatch._LITE_STATUS.clear()


async def test_unknown_workflow_raises() -> None:
    with pytest.raises(KeyError):
        await dispatch.dispatch_workflow("nope", args=[], workflow_id="x")


async def test_lite_schedules_in_process_and_completes() -> None:
    run = AsyncMock()
    with (
        patch.object(dispatch, "get_settings", return_value=_LITE),
        patch.object(dispatch, "run_sequence", run),
    ):
        result = await dispatch.dispatch_workflow(
            "ingest", args=["asset-1"], workflow_id="ingest-1"
        )
        # returns immediately; work is in flight
        assert result.status == "queued"
        assert dispatch.lite_workflow_status("ingest-1").status == "running"
        await dispatch.drain_background_tasks()

    run.assert_awaited_once_with(INGEST, ["asset-1"])
    assert dispatch.lite_workflow_status("ingest-1").status == "completed"


async def test_lite_failure_is_logged_not_raised() -> None:
    run = AsyncMock(side_effect=RuntimeError("kaboom"))
    with (
        patch.object(dispatch, "get_settings", return_value=_LITE),
        patch.object(dispatch, "run_sequence", run),
    ):
        result = await dispatch.dispatch_workflow(
            "ocr", args=["asset-1"], workflow_id="ocr-1"
        )
        assert result.status == "queued"
        await dispatch.drain_background_tasks()

    status = dispatch.lite_workflow_status("ocr-1")
    assert status.status == "failed"
    assert status.error_code == "processing_error"
    assert "kaboom" in status.error_message


async def test_lite_engine_failure_carries_remedy() -> None:
    """a missing engine surfaces its remedy through the status map."""
    run = AsyncMock(
        side_effect=EngineUnavailableError(
            "transcription", "install the ai extra"
        )
    )
    with (
        patch.object(dispatch, "get_settings", return_value=_LITE),
        patch.object(dispatch, "run_sequence", run),
    ):
        await dispatch.dispatch_workflow(
            "transcription", args=["asset-1"], workflow_id="transcribe-1"
        )
        await dispatch.drain_background_tasks()

    status = dispatch.lite_workflow_status("transcribe-1")
    assert status.status == "failed"
    assert status.error_code == "engine_unavailable"
    assert status.error_message == "install the ai extra"


async def test_server_starts_temporal_workflow() -> None:
    client = AsyncMock()
    client.start_workflow = AsyncMock()
    with (
        patch.object(dispatch, "get_settings", return_value=_SERVER),
        patch(
            "temporalio.client.Client.connect",
            AsyncMock(return_value=client),
        ),
    ):
        result = await dispatch.dispatch_workflow(
            "ingest", args=["asset-1"], workflow_id="ingest-1"
        )

    assert result.status == "queued"
    client.start_workflow.assert_awaited_once()
    kwargs = client.start_workflow.await_args.kwargs
    assert kwargs["id"] == "ingest-1"
    assert kwargs["task_queue"] == "loom-ingest"
    assert kwargs["args"] == ["asset-1"]


async def test_server_export_uses_string_reference() -> None:
    client = AsyncMock()
    client.start_workflow = AsyncMock()
    with (
        patch.object(dispatch, "get_settings", return_value=_SERVER),
        patch(
            "temporalio.client.Client.connect",
            AsyncMock(return_value=client),
        ),
    ):
        await dispatch.dispatch_workflow(
            "export", args=["export-1"], workflow_id="export-1"
        )

    ref = client.start_workflow.await_args.args[0]
    assert ref == "ExportWorkflow"
