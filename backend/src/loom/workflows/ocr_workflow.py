from datetime import timedelta

from temporalio import workflow
from temporalio.common import RetryPolicy

with workflow.unsafe.imports_passed_through():
    from loom.workflows.ocr_activities import (
        prepare_ocr_input,
        run_ocr,
        store_ocr_results,
    )


@workflow.defn
class OcrWorkflow:  # pragma: no cover
    """orchestrates ocr processing for an asset.

    steps: prepare input -> run ocr -> store results.
    """

    @workflow.run
    async def run(self, asset_id: str) -> str:  # pragma: no cover
        # step 1: extract frames (for video) or prepare images
        await workflow.execute_activity(
            prepare_ocr_input,
            asset_id,
            start_to_close_timeout=timedelta(minutes=30),
        )

        # step 2: run ocr
        await workflow.execute_activity(
            run_ocr,
            asset_id,
            start_to_close_timeout=timedelta(hours=1),
            retry_policy=RetryPolicy(
                maximum_attempts=2,
            ),
        )

        # step 3: store results
        await workflow.execute_activity(
            store_ocr_results,
            asset_id,
            start_to_close_timeout=timedelta(minutes=5),
        )

        return asset_id
