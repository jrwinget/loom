from temporalio import workflow

with workflow.unsafe.imports_passed_through():
    from loom.workflows.sequences import EXPORT
    from loom.workflows.temporal_driver import execute_spec


@workflow.defn
class ExportWorkflow:  # pragma: no cover
    """orchestrates export bundle generation."""

    @workflow.run
    async def run(self, export_id: str) -> str:  # pragma: no cover
        await execute_spec(EXPORT, [export_id])
        return export_id
