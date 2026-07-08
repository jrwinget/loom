"""ingest workflow execution order and configuration tests.

the orchestration now lives in loom.workflows.sequences (consumed
by both the temporal driver and the lite in-process runner), so
these assertions read the spec rather than the workflow source.
end-to-end execution order is additionally proven against a real
temporal env in tests/integration/workflows/test_ingest_workflow_e2e.py.
"""

import inspect

from loom.workflows.ingest_workflow import IngestWorkflow
from loom.workflows.sequences import INGEST


def _activity_names() -> list[str]:
    return [step.activity.__name__ for step in INGEST.steps]


def _by_name() -> dict:
    return {step.activity.__name__: step for step in INGEST.steps}


# ── activity execution order ──────────────────────────────


class TestActivityExecutionOrder:
    """verify activities execute in the correct pipeline order."""

    def test_five_activities_in_pipeline(self) -> None:
        assert len(INGEST.steps) == 5

    def test_hash_verification_runs_first(self) -> None:
        assert _activity_names()[0] == "verify_asset_hash"

    def test_metadata_extraction_runs_second(self) -> None:
        assert _activity_names()[1] == "extract_asset_metadata"

    def test_proxy_generation_runs_third(self) -> None:
        assert _activity_names()[2] == "generate_asset_proxies"

    def test_custody_recording_runs_fourth(self) -> None:
        assert _activity_names()[3] == "record_derivatives_custody"

    def test_mark_complete_runs_last(self) -> None:
        assert _activity_names()[4] == "mark_asset_complete"

    def test_full_pipeline_order(self) -> None:
        assert _activity_names() == [
            "verify_asset_hash",
            "extract_asset_metadata",
            "generate_asset_proxies",
            "record_derivatives_custody",
            "mark_asset_complete",
        ]


# ── workflow configuration ────────────────────────────────


class TestWorkflowConfiguration:
    """verify workflow activity configuration."""

    def test_all_activities_have_timeout(self) -> None:
        for step in INGEST.steps:
            assert step.timeout_s > 0, (
                f"{step.activity.__name__} missing timeout"
            )

    def test_hash_verify_has_retry_policy(self) -> None:
        assert _by_name()["verify_asset_hash"].max_attempts == 3

    def test_metadata_has_retry_policy(self) -> None:
        assert _by_name()["extract_asset_metadata"].max_attempts == 3

    def test_proxy_gen_has_retry_policy(self) -> None:
        assert _by_name()["generate_asset_proxies"].max_attempts == 2

    def test_proxy_gen_has_longest_timeout(self) -> None:
        longest = max(INGEST.steps, key=lambda s: s.timeout_s)
        assert longest.activity.__name__ == "generate_asset_proxies"
        assert longest.timeout_s == 1800

    def test_custody_and_complete_are_fast(self) -> None:
        by_name = _by_name()
        assert by_name["record_derivatives_custody"].timeout_s == 120
        assert by_name["mark_asset_complete"].timeout_s == 120


# ── workflow definition ───────────────────────────────────


class TestWorkflowDefinition:
    """verify workflow class structure."""

    def test_workflow_returns_asset_id(self) -> None:
        sig = inspect.signature(IngestWorkflow.run)
        assert sig.return_annotation is str

    def test_workflow_accepts_single_arg(self) -> None:
        sig = inspect.signature(IngestWorkflow.run)
        params = list(sig.parameters.keys())
        assert params == ["self", "asset_id"]

    def test_all_pipeline_activities_present(self) -> None:
        expected = {
            "verify_asset_hash",
            "extract_asset_metadata",
            "generate_asset_proxies",
            "record_derivatives_custody",
            "mark_asset_complete",
        }
        assert set(_activity_names()) == expected
