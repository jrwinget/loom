from temporalio import workflow

with workflow.unsafe.imports_passed_through():
    from loom.workflows.sequences import INGEST
    from loom.workflows.temporal_driver import execute_spec


@workflow.defn
class IngestWorkflow:
    """orchestrates the full ingest pipeline for an asset.

    steps: hash verification -> metadata extraction ->
    proxy generation -> custody recording -> mark complete.
    the sequence lives in loom.workflows.sequences so the
    in-process lite runner executes the identical steps.
    """

    @workflow.run
    async def run(self, asset_id: str) -> str:
        await execute_spec(INGEST, [asset_id])
        return asset_id
