"""Temporal workflow for URL-sourced ingestion (issue #46)."""

from datetime import timedelta

from temporalio import workflow
from temporalio.common import RetryPolicy

with workflow.unsafe.imports_passed_through():
    from loom.workflows.ingest_activities import (
        extract_asset_metadata,
        generate_asset_proxies,
        mark_asset_complete,
        record_derivatives_custody,
        verify_asset_hash,
    )
    from loom.workflows.url_ingest_activities import (
        attempt_wayback_snapshot,
        download_url_and_record_provenance,
    )


@workflow.defn
class UrlIngestWorkflow:
    """Download a URL, snapshot Wayback, run the ingest pipeline.

    Mirrors IngestWorkflow after the bytes are on disk so all
    downstream processing (hash verification, metadata extraction,
    proxy generation, custody, completion) is identical. Wayback
    is a separate non-blocking step and never retries.
    """

    @workflow.run
    async def run(self, asset_id: str, url: str) -> str:
        # step 1: download + record provenance
        await workflow.execute_activity(
            download_url_and_record_provenance,
            args=[asset_id, url],
            start_to_close_timeout=timedelta(minutes=30),
            retry_policy=RetryPolicy(maximum_attempts=3),
        )

        # step 2: wayback snapshot (best-effort, single attempt)
        await workflow.execute_activity(
            attempt_wayback_snapshot,
            args=[asset_id, url],
            start_to_close_timeout=timedelta(seconds=60),
            retry_policy=RetryPolicy(maximum_attempts=1),
        )

        # step 3: hand off to the standard ingest pipeline
        await workflow.execute_activity(
            verify_asset_hash,
            asset_id,
            start_to_close_timeout=timedelta(minutes=10),
            retry_policy=RetryPolicy(maximum_attempts=3),
        )
        await workflow.execute_activity(
            extract_asset_metadata,
            asset_id,
            start_to_close_timeout=timedelta(minutes=5),
            retry_policy=RetryPolicy(maximum_attempts=3),
        )
        await workflow.execute_activity(
            generate_asset_proxies,
            asset_id,
            start_to_close_timeout=timedelta(minutes=30),
            heartbeat_timeout=timedelta(minutes=2),
            retry_policy=RetryPolicy(maximum_attempts=2),
        )
        await workflow.execute_activity(
            record_derivatives_custody,
            asset_id,
            start_to_close_timeout=timedelta(minutes=2),
            retry_policy=RetryPolicy(maximum_attempts=3),
        )
        await workflow.execute_activity(
            mark_asset_complete,
            asset_id,
            start_to_close_timeout=timedelta(minutes=2),
            retry_policy=RetryPolicy(maximum_attempts=3),
        )

        return asset_id
