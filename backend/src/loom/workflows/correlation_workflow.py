from datetime import timedelta

from temporalio import workflow

with workflow.unsafe.imports_passed_through():
    from loom.workflows.correlation_activities import (
        correlate_case_assets,
    )


@workflow.defn
class CorrelationWorkflow:
    """orchestrates multi-perspective correlation for a case.

    runs the correlation activity which computes candidate
    groupings across the case's assets and persists them as
    pending for human review. never auto-merges; reviewers
    accept or reject each candidate.
    """

    @workflow.run
    async def run(self, case_id: str) -> int:
        return await workflow.execute_activity(
            correlate_case_assets,
            case_id,
            start_to_close_timeout=timedelta(minutes=15),
        )
