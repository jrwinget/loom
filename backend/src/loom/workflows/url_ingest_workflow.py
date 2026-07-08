"""Temporal workflow for URL-sourced ingestion (issue #46)."""

from temporalio import workflow

with workflow.unsafe.imports_passed_through():
    from loom.workflows.sequences import URL_INGEST
    from loom.workflows.temporal_driver import execute_spec


@workflow.defn
class UrlIngestWorkflow:
    """Download a URL, snapshot Wayback, run the ingest pipeline.

    Mirrors IngestWorkflow after the bytes are on disk so all
    downstream processing (hash verification, metadata extraction,
    proxy generation, custody, completion) is identical — the
    shared INGEST tail in loom.workflows.sequences guarantees it.
    Wayback is a separate non-blocking step and never retries.
    """

    @workflow.run
    async def run(self, asset_id: str, url: str) -> str:
        await execute_spec(URL_INGEST, [asset_id, url])
        return asset_id
