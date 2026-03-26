import asyncio

from temporalio.client import Client
from temporalio.worker import Worker

from loom.config import get_settings
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


async def main() -> None:
    """start the temporal worker for the loom ingest queue."""
    settings = get_settings()
    client = await Client.connect(settings.temporal_host)
    worker = Worker(
        client,
        task_queue="loom-ingest",
        workflows=[IngestWorkflow, ExportWorkflow],
        activities=[
            verify_asset_hash,
            extract_asset_metadata,
            generate_asset_proxies,
            record_derivatives_custody,
            mark_asset_complete,
            build_export,
        ],
    )
    await worker.run()


if __name__ == "__main__":
    asyncio.run(main())
