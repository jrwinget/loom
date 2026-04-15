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


@workflow.defn
class IngestWorkflow:
    """orchestrates the full ingest pipeline for an asset.

    steps: hash verification -> metadata extraction ->
    proxy generation -> custody recording -> mark complete.
    """

    @workflow.run
    async def run(self, asset_id: str) -> str:
        # step 1: verify hash
        await workflow.execute_activity(
            verify_asset_hash,
            asset_id,
            start_to_close_timeout=timedelta(minutes=10),
            retry_policy=RetryPolicy(maximum_attempts=3),
        )

        # step 2: extract metadata
        await workflow.execute_activity(
            extract_asset_metadata,
            asset_id,
            start_to_close_timeout=timedelta(minutes=5),
            retry_policy=RetryPolicy(
                maximum_attempts=3,
                initial_interval=timedelta(seconds=10),
            ),
        )

        # step 3: generate proxies (long-running, with heartbeat)
        await workflow.execute_activity(
            generate_asset_proxies,
            asset_id,
            start_to_close_timeout=timedelta(minutes=30),
            heartbeat_timeout=timedelta(minutes=2),
            retry_policy=RetryPolicy(
                maximum_attempts=2,
                initial_interval=timedelta(seconds=60),
            ),
        )

        # step 4: record custody
        await workflow.execute_activity(
            record_derivatives_custody,
            asset_id,
            start_to_close_timeout=timedelta(minutes=2),
            retry_policy=RetryPolicy(
                maximum_attempts=3,
                initial_interval=timedelta(seconds=5),
            ),
        )

        # step 5: mark complete
        await workflow.execute_activity(
            mark_asset_complete,
            asset_id,
            start_to_close_timeout=timedelta(minutes=2),
            retry_policy=RetryPolicy(
                maximum_attempts=3,
                initial_interval=timedelta(seconds=5),
            ),
        )

        return asset_id
