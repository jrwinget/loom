"""end-to-end tests for ``IngestWorkflow`` against a temporal env.

these tests register the real workflow definition with a Worker
on the session-scoped time-skipping ``WorkflowEnvironment`` and
execute it. the activity implementations are replaced with
lightweight stubs (matched by ``@activity.defn(name=...)``) so
the workflow code path runs end to end without touching minio,
ffmpeg, or postgres. the goal is to prove orchestration
(activity ordering, retry policy, return value) — not to
re-test the activities themselves; those have dedicated unit
tests against their service layer.
"""

from typing import Any
from uuid import uuid4

import pytest_asyncio
from temporalio import activity
from temporalio.client import Client
from temporalio.worker import Worker

from loom.workflows.ingest_workflow import IngestWorkflow
from loom.workflows.url_ingest_workflow import UrlIngestWorkflow


@pytest_asyncio.fixture
def activity_call_log() -> list[str]:
    """per-test list capturing the order activities ran in."""
    return []


def _build_stub_activities(
    call_log: list[str],
    *,
    fail_first_metadata: bool = False,
) -> list[Any]:
    """build activity stubs matched by name to the originals.

    if ``fail_first_metadata`` is set, ``extract_asset_metadata``
    raises on its first invocation and succeeds on retry — used
    to exercise the workflow's retry policy.
    """
    state = {"metadata_attempts": 0}

    @activity.defn(name="verify_asset_hash")
    async def verify_asset_hash(asset_id: str) -> bool:
        call_log.append("verify_asset_hash")
        return True

    @activity.defn(name="extract_asset_metadata")
    async def extract_asset_metadata(asset_id: str) -> dict[str, Any]:
        state["metadata_attempts"] += 1
        if fail_first_metadata and state["metadata_attempts"] == 1:
            # raise a non-retryable-looking application error; the
            # workflow's RetryPolicy is maximum_attempts=3 so this
            # should be retried automatically.
            raise RuntimeError("transient metadata extractor blip")
        call_log.append("extract_asset_metadata")
        return {"raw": {}, "normalized": {}}

    @activity.defn(name="generate_asset_proxies")
    async def generate_asset_proxies(asset_id: str) -> list[str]:
        call_log.append("generate_asset_proxies")
        return [f"{asset_id}/proxy.mp4"]

    @activity.defn(name="record_derivatives_custody")
    async def record_derivatives_custody(asset_id: str) -> None:
        call_log.append("record_derivatives_custody")

    @activity.defn(name="mark_asset_complete")
    async def mark_asset_complete(asset_id: str) -> None:
        call_log.append("mark_asset_complete")

    return [
        verify_asset_hash,
        extract_asset_metadata,
        generate_asset_proxies,
        record_derivatives_custody,
        mark_asset_complete,
    ]


async def test_ingest_workflow_happy_path(
    temporal_client: Client,
    activity_call_log: list[str],
) -> None:
    """workflow runs all five activities in order and returns id."""
    asset_id = str(uuid4())
    task_queue = f"ingest-happy-{asset_id}"
    activities = _build_stub_activities(activity_call_log)

    async with Worker(
        temporal_client,
        task_queue=task_queue,
        workflows=[IngestWorkflow],
        activities=activities,
    ):
        result = await temporal_client.execute_workflow(
            IngestWorkflow.run,
            asset_id,
            id=f"ingest-{asset_id}",
            task_queue=task_queue,
        )

    assert result == asset_id
    assert activity_call_log == [
        "verify_asset_hash",
        "extract_asset_metadata",
        "generate_asset_proxies",
        "record_derivatives_custody",
        "mark_asset_complete",
    ]


async def test_ingest_workflow_retries_transient_activity_failure(
    temporal_client: Client,
    activity_call_log: list[str],
) -> None:
    """transient activity failure is retried per RetryPolicy."""
    asset_id = str(uuid4())
    task_queue = f"ingest-retry-{asset_id}"
    activities = _build_stub_activities(
        activity_call_log,
        fail_first_metadata=True,
    )

    async with Worker(
        temporal_client,
        task_queue=task_queue,
        workflows=[IngestWorkflow],
        activities=activities,
    ):
        result = await temporal_client.execute_workflow(
            IngestWorkflow.run,
            asset_id,
            id=f"ingest-{asset_id}",
            task_queue=task_queue,
        )

    # workflow still completes — first metadata attempt failed,
    # second succeeded, downstream activities ran exactly once.
    assert result == asset_id
    assert activity_call_log == [
        "verify_asset_hash",
        "extract_asset_metadata",
        "generate_asset_proxies",
        "record_derivatives_custody",
        "mark_asset_complete",
    ]


def _build_url_stub_activities(call_log: list[str]) -> list[Any]:
    """url-ingest stubs: the two url steps plus the shared tail."""

    @activity.defn(name="download_url_and_record_provenance")
    async def download(asset_id: str, url: str) -> dict[str, Any]:
        call_log.append("download_url_and_record_provenance")
        return {"asset_id": asset_id}

    @activity.defn(name="attempt_wayback_snapshot")
    async def wayback(asset_id: str, url: str) -> str | None:
        call_log.append("attempt_wayback_snapshot")
        return None

    return [download, wayback, *_build_stub_activities(call_log)]


async def test_url_ingest_workflow_runs_download_then_shared_tail(
    temporal_client: Client,
    activity_call_log: list[str],
) -> None:
    """url ingest downloads, snapshots, then runs the ingest tail."""
    asset_id = str(uuid4())
    url = "https://example.com/clip.mp4"
    task_queue = f"url-ingest-{asset_id}"
    activities = _build_url_stub_activities(activity_call_log)

    async with Worker(
        temporal_client,
        task_queue=task_queue,
        workflows=[UrlIngestWorkflow],
        activities=activities,
    ):
        result = await temporal_client.execute_workflow(
            UrlIngestWorkflow.run,
            args=[asset_id, url],
            id=f"url-ingest-{asset_id}",
            task_queue=task_queue,
        )

    assert result == asset_id
    assert activity_call_log == [
        "download_url_and_record_provenance",
        "attempt_wayback_snapshot",
        "verify_asset_hash",
        "extract_asset_metadata",
        "generate_asset_proxies",
        "record_derivatives_custody",
        "mark_asset_complete",
    ]
