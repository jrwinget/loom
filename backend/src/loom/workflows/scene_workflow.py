from temporalio import workflow

with workflow.unsafe.imports_passed_through():
    from loom.workflows.sequences import SCENE_DETECTION
    from loom.workflows.temporal_driver import execute_spec


@workflow.defn
class SceneDetectionWorkflow:  # pragma: no cover
    """orchestrates scene detection for a video asset.

    steps: detect boundaries -> generate thumbnails ->
    store results in db.
    """

    @workflow.run
    async def run(self, asset_id: str) -> str:  # pragma: no cover
        await execute_spec(SCENE_DETECTION, [asset_id])
        return asset_id
