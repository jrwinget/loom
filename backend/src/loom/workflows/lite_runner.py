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
from typing import Any
from uuid import UUID

from sqlalchemy import select

from loom.models.asset import Asset
from loom.workflows.sequences import Step, WorkflowSpec
from loom.workflows.shared import get_db_session

logger = logging.getLogger(__name__)


async def run_sequence(spec: WorkflowSpec, workflow_args: list[Any]) -> None:
    """run every step of ``spec`` in order, in-process.

    raises the originating exception if a step fails after its
    retries are exhausted; callers schedule this fire-and-forget and
    are responsible for catching and logging.
    """
    if spec.asset_status_arg is not None:
        await _set_asset_status(
            workflow_args[spec.asset_status_arg], "processing"
        )

    try:
        results: dict[str, Any] = {}
        for step in spec.steps:
            call_args = step.bind(workflow_args, results)
            results[step.key] = await _call_with_retries(step, call_args)
    except Exception:
        if spec.asset_status_arg is not None:
            await _set_asset_status(
                workflow_args[spec.asset_status_arg], "failed"
            )
        raise


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


async def _set_asset_status(asset_id: str, status: str) -> None:
    """advance an asset's processing_status (best-effort)."""
    async with get_db_session() as session:
        result = await session.execute(
            select(Asset).where(Asset.id == UUID(asset_id))
        )
        asset = result.scalar_one_or_none()
        if asset is None:
            return
        asset.processing_status = status
        await session.commit()
