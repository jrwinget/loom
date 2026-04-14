import inspect

from loom.workflows.ingest_activities import (
    extract_asset_metadata,
    generate_asset_proxies,
    mark_asset_complete,
    record_derivatives_custody,
    verify_asset_hash,
)
from loom.workflows.ingest_workflow import IngestWorkflow


class TestIngestWorkflowDefinition:
    """test that IngestWorkflow is properly defined."""

    def test_workflow_class_exists(self) -> None:
        assert IngestWorkflow is not None

    def test_workflow_has_run_method(self) -> None:
        assert hasattr(IngestWorkflow, "run")

    def test_run_is_async(self) -> None:
        assert inspect.iscoroutinefunction(IngestWorkflow.run)

    def test_run_takes_asset_id(self) -> None:
        sig = inspect.signature(IngestWorkflow.run)
        params = list(sig.parameters.keys())
        assert "asset_id" in params


class TestActivityDecorators:
    """test that activities have correct decorators."""

    def test_verify_asset_hash_is_activity(self) -> None:
        assert hasattr(verify_asset_hash, "__temporal_activity_definition")

    def test_extract_metadata_is_activity(self) -> None:
        assert hasattr(
            extract_asset_metadata,
            "__temporal_activity_definition",
        )

    def test_generate_proxies_is_activity(self) -> None:
        assert hasattr(
            generate_asset_proxies,
            "__temporal_activity_definition",
        )

    def test_record_custody_is_activity(self) -> None:
        assert hasattr(
            record_derivatives_custody,
            "__temporal_activity_definition",
        )

    def test_mark_complete_is_activity(self) -> None:
        assert hasattr(
            mark_asset_complete,
            "__temporal_activity_definition",
        )


class TestActivitySignatures:
    """test that activities have correct signatures."""

    def test_verify_hash_takes_asset_id(self) -> None:
        sig = inspect.signature(verify_asset_hash)
        params = list(sig.parameters.keys())
        assert "asset_id" in params

    def test_extract_metadata_takes_asset_id(
        self,
    ) -> None:
        sig = inspect.signature(extract_asset_metadata)
        params = list(sig.parameters.keys())
        assert "asset_id" in params

    def test_generate_proxies_takes_asset_id(
        self,
    ) -> None:
        sig = inspect.signature(generate_asset_proxies)
        params = list(sig.parameters.keys())
        assert "asset_id" in params

    def test_record_custody_takes_asset_id(self) -> None:
        sig = inspect.signature(record_derivatives_custody)
        params = list(sig.parameters.keys())
        assert "asset_id" in params

    def test_mark_complete_takes_asset_id(self) -> None:
        sig = inspect.signature(mark_asset_complete)
        params = list(sig.parameters.keys())
        assert "asset_id" in params

    def test_all_activities_are_async(self) -> None:
        for fn in [
            verify_asset_hash,
            extract_asset_metadata,
            generate_asset_proxies,
            record_derivatives_custody,
            mark_asset_complete,
        ]:
            assert inspect.iscoroutinefunction(fn), (
                f"{fn.__name__} should be async"
            )
