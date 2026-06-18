from temporalio import workflow

with workflow.unsafe.imports_passed_through():
    from loom.workflows.sequences import OCR
    from loom.workflows.temporal_driver import execute_spec


@workflow.defn
class OcrWorkflow:  # pragma: no cover
    """orchestrates ocr processing for an asset.

    steps: prepare input -> run ocr -> store results.
    """

    @workflow.run
    async def run(self, asset_id: str) -> str:  # pragma: no cover
        await execute_spec(OCR, [asset_id])
        return asset_id
