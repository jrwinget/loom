from temporalio import workflow

with workflow.unsafe.imports_passed_through():
    from loom.workflows.sequences import BUNDLE_IMPORT
    from loom.workflows.temporal_driver import execute_spec


@workflow.defn
class BundleImportWorkflow:  # pragma: no cover
    """recreates a case from a verified portable bundle."""

    @workflow.run
    async def run(self, case_id: str) -> str:  # pragma: no cover
        await execute_spec(BUNDLE_IMPORT, [case_id])
        return case_id
