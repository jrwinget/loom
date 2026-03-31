"""ingest workflow configuration and execution tests."""

import inspect

from loom.workflows.ingest_activities import (
    extract_asset_metadata,
    generate_asset_proxies,
    mark_asset_complete,
    record_derivatives_custody,
    verify_asset_hash,
)
from loom.workflows.ingest_workflow import IngestWorkflow


class TestActivityRegistration:
    """all activities must be registered with temporal."""

    def test_verify_hash_is_activity(self) -> None:
        """verify_asset_hash is a temporal activity."""
        assert hasattr(
            verify_asset_hash,
            "__temporal_activity_definition",
        )

    def test_extract_metadata_is_activity(self) -> None:
        """extract_asset_metadata is a temporal activity."""
        assert hasattr(
            extract_asset_metadata,
            "__temporal_activity_definition",
        )

    def test_generate_proxies_is_activity(self) -> None:
        """generate_asset_proxies is a temporal activity."""
        assert hasattr(
            generate_asset_proxies,
            "__temporal_activity_definition",
        )

    def test_record_custody_is_activity(self) -> None:
        """record_derivatives_custody is a temporal activity."""
        assert hasattr(
            record_derivatives_custody,
            "__temporal_activity_definition",
        )

    def test_mark_complete_is_activity(self) -> None:
        """mark_asset_complete is a temporal activity."""
        assert hasattr(
            mark_asset_complete,
            "__temporal_activity_definition",
        )


class TestWorkflowRegistration:
    """workflow must be registered with temporal."""

    def test_ingest_workflow_is_defn(self) -> None:
        """IngestWorkflow has temporal workflow definition."""
        assert hasattr(
            IngestWorkflow,
            "__temporal_workflow_definition",
        )

    def test_run_is_async(self) -> None:
        """workflow run method must be async."""
        assert inspect.iscoroutinefunction(IngestWorkflow.run)


class TestWorkflowConfiguration:
    """verify retry policies and timeouts in source."""

    def test_workflow_source_has_heartbeat(self) -> None:
        """proxy generation activity should reference
        heartbeat_timeout in the workflow source."""
        source = inspect.getsource(IngestWorkflow.run)
        assert "heartbeat_timeout" in source

    def test_workflow_source_has_retry_for_custody(
        self,
    ) -> None:
        """record_custody step should have retry policy."""
        source = inspect.getsource(IngestWorkflow.run)
        # find the custody section
        custody_idx = source.index("record_derivatives_custody")
        remaining = source[custody_idx:]
        # should have retry_policy before next activity
        complete_idx = remaining.index("mark_asset_complete")
        custody_section = remaining[:complete_idx]
        assert "RetryPolicy" in custody_section

    def test_workflow_source_has_retry_for_complete(
        self,
    ) -> None:
        """mark_complete step should have retry policy."""
        source = inspect.getsource(IngestWorkflow.run)
        complete_idx = source.index("mark_asset_complete")
        remaining = source[complete_idx:]
        assert "RetryPolicy" in remaining

    def test_all_five_activities_present(self) -> None:
        """workflow must execute all five pipeline steps."""
        source = inspect.getsource(IngestWorkflow.run)
        assert "verify_asset_hash" in source
        assert "extract_asset_metadata" in source
        assert "generate_asset_proxies" in source
        assert "record_derivatives_custody" in source
        assert "mark_asset_complete" in source
