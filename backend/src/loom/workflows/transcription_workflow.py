from temporalio import workflow

with workflow.unsafe.imports_passed_through():
    from loom.workflows.sequences import TRANSCRIPTION
    from loom.workflows.temporal_driver import execute_spec


@workflow.defn
class TranscriptionWorkflow:
    """orchestrates audio transcription and diarization.

    steps: extract audio -> transcribe -> diarize ->
    store results. the extracted audio path threads from the
    first step into transcribe/diarize via the shared sequence.
    """

    @workflow.run
    async def run(self, asset_id: str) -> str:
        await execute_spec(TRANSCRIPTION, [asset_id])
        return asset_id
