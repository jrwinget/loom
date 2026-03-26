from datetime import timedelta

from temporalio import workflow
from temporalio.common import RetryPolicy

with workflow.unsafe.imports_passed_through():
    from loom.workflows.export_activities import build_export


@workflow.defn
class ExportWorkflow:
    """orchestrates export bundle generation."""

    @workflow.run
    async def run(self, export_id: str) -> str:
        await workflow.execute_activity(
            build_export,
            export_id,
            start_to_close_timeout=timedelta(minutes=60),
            retry_policy=RetryPolicy(max_attempts=2),
        )
        return export_id
