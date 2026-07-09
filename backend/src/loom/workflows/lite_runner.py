"""in-process execution of workflow sequences for the lite profile.

the lite (desktop) profile has no temporal server. these helpers
run the same activity functions a temporal worker would, in order,
directly in the api process. activities already open their own
profile-aware db sessions and storage backend (see
loom.workflows.shared), so they need no worker context.

server-only concerns are intentionally dropped: durable timers and
cross-restart retries don't exist in-process. retries honour each
step's max_attempts (a step with no explicit policy runs once so a
deterministic failure can't loop forever), and the asset's
processing_status is advanced so the desktop ui reflects progress.
"""

import logging
from collections.abc import Callable
from typing import Any
from uuid import UUID

from sqlalchemy import select

from loom.models.asset import Asset
from loom.services.engines import EngineUnavailableError
from loom.workflows.sequences import Step, WorkflowSpec
from loom.workflows.shared import get_db_session

logger = logging.getLogger(__name__)

# (stage, steps_done, steps_total) as each step starts
ProgressCallback = Callable[[str, int, int], None]


async def run_sequence(
    spec: WorkflowSpec,
    workflow_args: list[Any],
    on_step: ProgressCallback | None = None,
) -> None:
    """run every step of ``spec`` in order, in-process.

    raises the originating exception if a step fails after its
    retries are exhausted; callers schedule this fire-and-forget and
    are responsible for catching and logging. ``on_step`` fires as
    each step starts so the status map can report progress.
    """
    if spec.asset_status_arg is not None:
        await _set_asset_status(
            workflow_args[spec.asset_status_arg], "processing"
        )

    try:
        results: dict[str, Any] = {}
        total = len(spec.steps)
        for done, step in enumerate(spec.steps):
            if on_step is not None:
                on_step(step.activity.__name__, done, total)
            call_args = step.bind(workflow_args, results)
            results[step.key] = await _call_with_retries(step, call_args)
    except Exception as exc:
        if spec.asset_status_arg is not None:
            await _set_asset_status(
                workflow_args[spec.asset_status_arg],
                "failed",
                error=_failure_reason(exc),
            )
        raise


def _failure_reason(exc: Exception) -> str:
    """user-facing reason recorded on the asset row."""
    if isinstance(exc, EngineUnavailableError):
        return exc.remedy
    return str(exc)[:500] or exc.__class__.__name__


async def _call_with_retries(step: Step, call_args: list[Any]) -> Any:
    """invoke a step's activity, retrying up to its max_attempts."""
    attempts = step.max_attempts or 1
    last_exc: Exception | None = None
    for attempt in range(attempts):
        try:
            return await step.activity(*call_args)
        except Exception as exc:
            last_exc = exc
            logger.warning(
                "lite step %s attempt %d/%d failed: %s",
                step.activity.__name__,
                attempt + 1,
                attempts,
                exc,
            )
    assert last_exc is not None
    raise last_exc


async def _set_asset_status(
    asset_id: str,
    status: str,
    error: str | None = None,
) -> None:
    """advance an asset's processing_status (best-effort)."""
    async with get_db_session() as session:
        result = await session.execute(
            select(Asset).where(Asset.id == UUID(asset_id))
        )
        asset = result.scalar_one_or_none()
        if asset is None:
            return
        asset.processing_status = status
        # a fresh run clears the previous failure reason
        asset.processing_error = error
        await session.commit()
