"""drive a WorkflowSpec inside a temporal workflow.

each @workflow.defn class delegates to this so the activity
ordering, timeouts, and retry policy live in one place
(loom.workflows.sequences) rather than being re-typed per
workflow. imports here are limited to temporalio + datetime so
the module is safe to run inside the workflow sandbox.
"""

from datetime import timedelta
from typing import Any

from temporalio import workflow
from temporalio.common import RetryPolicy

from loom.workflows.sequences import WorkflowSpec


async def execute_spec(spec: WorkflowSpec, workflow_args: list[Any]) -> None:
    """execute every step of ``spec`` in order via temporal.

    later steps can read earlier steps' return values through the
    binder's ``results`` argument (keyed by ``Step.key``).
    """
    results: dict[str, Any] = {}
    for step in spec.steps:
        kwargs: dict[str, Any] = {
            "args": step.bind(workflow_args, results),
            "start_to_close_timeout": timedelta(seconds=step.timeout_s),
        }
        if step.heartbeat_s is not None:
            kwargs["heartbeat_timeout"] = timedelta(seconds=step.heartbeat_s)
        if step.max_attempts is not None:
            retry: dict[str, Any] = {"maximum_attempts": step.max_attempts}
            if step.initial_interval_s is not None:
                retry["initial_interval"] = timedelta(
                    seconds=step.initial_interval_s
                )
            kwargs["retry_policy"] = RetryPolicy(**retry)
        results[step.key] = await workflow.execute_activity(
            step.activity, **kwargs
        )
