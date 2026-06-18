"""profile-aware workflow dispatch.

every workflow-triggering endpoint calls :func:`dispatch_workflow`
instead of connecting to temporal directly. on the server profile
this starts a temporal workflow exactly as before; on the lite
(desktop) profile — which has no temporal server — it runs the
same activity sequence in-process (see loom.workflows.lite_runner).

this is the seam the desktop architecture always described but
never had: "the same activity functions run in-process behind a
thin temporal-shaped facade so the rest of the code doesn't branch
on profile" (docs/architecture.md).
"""

import asyncio
import logging
from dataclasses import dataclass
from typing import Any

from loom.config import get_settings
from loom.workflows.lite_runner import run_sequence
from loom.workflows.sequences import SPECS

logger = logging.getLogger(__name__)

TASK_QUEUE = "loom-ingest"

# lite-profile in-process state. background tasks are retained so
# they aren't garbage-collected mid-flight; the status map lets the
# workflow-status endpoint report progress with no temporal server
# to query. both are process-local and reset on restart, which is
# correct: an in-flight in-process workflow does not survive a
# restart either.
_BG_TASKS: set[asyncio.Task[None]] = set()
_LITE_STATUS: dict[str, str] = {}


@dataclass(frozen=True)
class DispatchResult:
    """outcome of a dispatch; ``status`` matches the queued contract."""

    workflow_id: str
    status: str


async def dispatch_workflow(
    name: str,
    *,
    args: list[Any],
    workflow_id: str,
) -> DispatchResult:
    """start a workflow on temporal (server) or in-process (lite).

    returns immediately with ``status="queued"``; the work runs in
    the background on both profiles. raises on the server profile if
    temporal is unreachable (the caller decides whether that is a
    502 or a non-fatal log).
    """
    if name not in SPECS:
        raise KeyError(f"unknown workflow: {name}")

    settings = get_settings()
    if settings.is_lite:
        _schedule_lite(name, args, workflow_id)
        return DispatchResult(workflow_id, "queued")

    from temporalio.client import Client

    client = await Client.connect(settings.temporal_host)
    await client.start_workflow(
        _server_ref(name),
        args=args,
        id=workflow_id,
        task_queue=TASK_QUEUE,
    )
    return DispatchResult(workflow_id, "queued")


def _server_ref(name: str) -> Any:
    """temporal start_workflow reference for a workflow name.

    imported lazily so the lite profile never loads the workflow
    sandbox machinery it doesn't use. export keeps its string
    reference to match the worker's registration exactly.
    """
    if name == "ingest":
        from loom.workflows.ingest_workflow import IngestWorkflow

        return IngestWorkflow.run
    if name == "url_ingest":
        from loom.workflows.url_ingest_workflow import UrlIngestWorkflow

        return UrlIngestWorkflow.run
    if name == "ocr":
        from loom.workflows.ocr_workflow import OcrWorkflow

        return OcrWorkflow.run
    if name == "transcription":
        from loom.workflows.transcription_workflow import (
            TranscriptionWorkflow,
        )

        return TranscriptionWorkflow.run
    if name == "scene_detection":
        from loom.workflows.scene_workflow import SceneDetectionWorkflow

        return SceneDetectionWorkflow.run
    if name == "export":
        return "ExportWorkflow"
    raise KeyError(f"unknown workflow: {name}")


def _schedule_lite(name: str, args: list[Any], workflow_id: str) -> None:
    """fire-and-forget the in-process runner for ``name``."""
    _LITE_STATUS[workflow_id] = "running"
    task = asyncio.create_task(
        _run_lite_safely(name, args, workflow_id),
        name=workflow_id,
    )
    _BG_TASKS.add(task)
    task.add_done_callback(_BG_TASKS.discard)


async def _run_lite_safely(
    name: str, args: list[Any], workflow_id: str
) -> None:
    """run a sequence in-process, recording terminal status.

    exceptions are logged, never raised: the http request that
    scheduled this has already returned, so there is no 502 to
    surface. the failure is visible via the status map and the
    asset's processing_status.
    """
    try:
        await run_sequence(SPECS[name], list(args))
        _LITE_STATUS[workflow_id] = "completed"
    except Exception:
        logger.error(
            "in-process %s workflow %s failed",
            name,
            workflow_id,
            exc_info=True,
        )
        _LITE_STATUS[workflow_id] = "failed"


def lite_workflow_status(workflow_id: str) -> str | None:
    """return the in-process status for a workflow, or None."""
    return _LITE_STATUS.get(workflow_id)


async def drain_background_tasks(timeout: float = 5.0) -> None:
    """best-effort wait for in-flight lite tasks on shutdown."""
    pending = [t for t in _BG_TASKS if not t.done()]
    if pending:
        await asyncio.wait(pending, timeout=timeout)
