from temporalio import workflow

with workflow.unsafe.imports_passed_through():
    from loom.workflows.sequences import ENHANCEMENT
    from loom.workflows.temporal_driver import execute_spec


@workflow.defn
class EnhancementWorkflow:  # pragma: no cover
    """orchestrates deterministic clarity-assist enhancement."""

    @workflow.run
    async def run(  # pragma: no cover
        self,
        asset_id: str,
        params_json: str,
    ) -> str:
        await execute_spec(ENHANCEMENT, [asset_id, params_json])
        return asset_id
