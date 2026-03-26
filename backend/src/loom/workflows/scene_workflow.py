from datetime import timedelta

from temporalio import workflow
from temporalio.common import RetryPolicy

with workflow.unsafe.imports_passed_through():
    from loom.workflows.scene_activities import (
        detect_asset_scenes,
        generate_scene_thumbs,
        store_scene_results,
    )


@workflow.defn
class SceneDetectionWorkflow:
    """orchestrates scene detection for a video asset.

    steps: detect boundaries -> generate thumbnails ->
    store results in db.
    """

    @workflow.run
    async def run(self, asset_id: str) -> str:
        # step 1: detect scene boundaries
        await workflow.execute_activity(
            detect_asset_scenes,
            asset_id,
            start_to_close_timeout=timedelta(minutes=30),
            retry_policy=RetryPolicy(maximum_attempts=2),
        )

        # step 2: generate thumbnails for each scene
        await workflow.execute_activity(
            generate_scene_thumbs,
            asset_id,
            start_to_close_timeout=timedelta(minutes=15),
        )

        # step 3: persist scene records
        await workflow.execute_activity(
            store_scene_results,
            asset_id,
            start_to_close_timeout=timedelta(minutes=5),
        )

        return asset_id
