from datetime import timedelta

from temporalio import workflow
from temporalio.common import RetryPolicy

with workflow.unsafe.imports_passed_through():
    from loom.workflows.transcription_activities import (
        diarize_asset,
        extract_audio,
        store_transcript,
        transcribe_asset,
    )


@workflow.defn
class TranscriptionWorkflow:
    """orchestrates audio transcription and diarization.

    steps: extract audio -> transcribe -> diarize ->
    store results.
    """

    @workflow.run
    async def run(self, asset_id: str) -> str:
        # step 1: extract audio from video (if video)
        audio_path = await workflow.execute_activity(
            extract_audio,
            asset_id,
            start_to_close_timeout=timedelta(minutes=30),
            retry_policy=RetryPolicy(
                maximum_attempts=2,
            ),
        )

        # step 2: transcribe
        await workflow.execute_activity(
            transcribe_asset,
            args=[asset_id, audio_path],
            start_to_close_timeout=timedelta(hours=2),
            retry_policy=RetryPolicy(
                maximum_attempts=2,
            ),
        )

        # step 3: diarize (optional, best-effort)
        await workflow.execute_activity(
            diarize_asset,
            args=[asset_id, audio_path],
            start_to_close_timeout=timedelta(hours=1),
            retry_policy=RetryPolicy(
                maximum_attempts=1,
            ),
        )

        # step 4: store results
        await workflow.execute_activity(
            store_transcript,
            asset_id,
            start_to_close_timeout=timedelta(minutes=5),
        )

        return asset_id
