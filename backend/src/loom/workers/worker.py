import asyncio

from temporalio.client import Client
from temporalio.worker import Worker

from loom.config import get_settings
from loom.workflows.correlation_activities import (
    correlate_case_assets,
)
from loom.workflows.correlation_workflow import CorrelationWorkflow
from loom.workflows.export_activities import build_export
from loom.workflows.export_workflow import ExportWorkflow
from loom.workflows.ingest_activities import (
    extract_asset_metadata,
    generate_asset_proxies,
    mark_asset_complete,
    record_derivatives_custody,
    verify_asset_hash,
)
from loom.workflows.ingest_workflow import IngestWorkflow
from loom.workflows.ocr_activities import (
    prepare_ocr_input,
    run_ocr,
    store_ocr_results,
)
from loom.workflows.ocr_workflow import OcrWorkflow
from loom.workflows.scene_activities import (
    detect_asset_scenes,
    generate_scene_thumbs,
    store_scene_results,
)
from loom.workflows.scene_workflow import SceneDetectionWorkflow
from loom.workflows.transcription_activities import (
    diarize_asset,
    extract_audio,
    store_transcript,
    transcribe_asset,
)
from loom.workflows.transcription_workflow import (
    TranscriptionWorkflow,
)
from loom.workflows.url_ingest_activities import (
    attempt_wayback_snapshot,
    download_url_and_record_provenance,
)
from loom.workflows.url_ingest_workflow import UrlIngestWorkflow


async def main() -> None:  # pragma: no cover
    """start the temporal worker for the loom ingest queue."""
    settings = get_settings()
    client = await Client.connect(settings.temporal_host)
    worker = Worker(
        client,
        task_queue="loom-ingest",
        workflows=[
            IngestWorkflow,
            ExportWorkflow,
            TranscriptionWorkflow,
            OcrWorkflow,
            SceneDetectionWorkflow,
            CorrelationWorkflow,
            UrlIngestWorkflow,
        ],
        activities=[
            verify_asset_hash,
            extract_asset_metadata,
            generate_asset_proxies,
            record_derivatives_custody,
            mark_asset_complete,
            build_export,
            extract_audio,
            transcribe_asset,
            diarize_asset,
            store_transcript,
            prepare_ocr_input,
            run_ocr,
            store_ocr_results,
            detect_asset_scenes,
            generate_scene_thumbs,
            store_scene_results,
            correlate_case_assets,
            download_url_and_record_provenance,
            attempt_wayback_snapshot,
        ],
    )
    await worker.run()


if __name__ == "__main__":
    asyncio.run(main())
