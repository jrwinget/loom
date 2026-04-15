"""ingest workflow execution order and configuration tests."""

import ast
import inspect
from pathlib import Path

from loom.workflows.ingest_workflow import IngestWorkflow


def _parse_workflow_source() -> ast.Module:
    """parse the ingest workflow source into an AST."""
    src_path = Path(inspect.getfile(IngestWorkflow))
    return ast.parse(src_path.read_text())


def _extract_activity_calls(
    tree: ast.Module,
) -> list[str]:
    """extract activity function names from
    execute_activity calls in source order."""
    names: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Await):
            continue
        call = node.value
        if not isinstance(call, ast.Call):
            continue
        func = call.func
        if not isinstance(func, ast.Attribute):
            continue
        if func.attr != "execute_activity":
            continue
        # first positional arg is the activity reference
        if call.args:
            arg = call.args[0]
            if isinstance(arg, ast.Name):
                names.append(arg.id)
    return names


# ── activity execution order ──────────────────────────────


class TestActivityExecutionOrder:
    """verify activities execute in the correct pipeline
    order."""

    def test_five_activities_in_pipeline(self) -> None:
        """ingest pipeline must have exactly 5 activity
        steps."""
        tree = _parse_workflow_source()
        activities = _extract_activity_calls(tree)
        assert len(activities) == 5

    def test_hash_verification_runs_first(self) -> None:
        """hash verification must be the first step."""
        tree = _parse_workflow_source()
        activities = _extract_activity_calls(tree)
        assert activities[0] == "verify_asset_hash"

    def test_metadata_extraction_runs_second(self) -> None:
        """metadata extraction must follow hash
        verification."""
        tree = _parse_workflow_source()
        activities = _extract_activity_calls(tree)
        assert activities[1] == "extract_asset_metadata"

    def test_proxy_generation_runs_third(self) -> None:
        """proxy generation must follow metadata
        extraction."""
        tree = _parse_workflow_source()
        activities = _extract_activity_calls(tree)
        assert activities[2] == "generate_asset_proxies"

    def test_custody_recording_runs_fourth(self) -> None:
        """custody recording must follow proxy generation."""
        tree = _parse_workflow_source()
        activities = _extract_activity_calls(tree)
        assert activities[3] == "record_derivatives_custody"

    def test_mark_complete_runs_last(self) -> None:
        """mark complete must be the final step."""
        tree = _parse_workflow_source()
        activities = _extract_activity_calls(tree)
        assert activities[4] == "mark_asset_complete"

    def test_full_pipeline_order(self) -> None:
        """verify the entire pipeline order in one shot."""
        tree = _parse_workflow_source()
        activities = _extract_activity_calls(tree)
        assert activities == [
            "verify_asset_hash",
            "extract_asset_metadata",
            "generate_asset_proxies",
            "record_derivatives_custody",
            "mark_asset_complete",
        ]


# ── workflow configuration ────────────────────────────────


def _extract_execute_activity_kwargs(
    tree: ast.Module,
) -> list[dict[str, object]]:
    """extract keyword arguments from each
    execute_activity call."""
    results: list[dict[str, object]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Await):
            continue
        call = node.value
        if not isinstance(call, ast.Call):
            continue
        func = call.func
        if not isinstance(func, ast.Attribute):
            continue
        if func.attr != "execute_activity":
            continue
        kwargs: dict[str, object] = {}
        # capture activity name
        if call.args and isinstance(call.args[0], ast.Name):
            kwargs["_activity"] = call.args[0].id
        for kw in call.keywords:
            kwargs[kw.arg] = kw.arg  # just record presence
        results.append(kwargs)
    return results


class TestWorkflowConfiguration:
    """verify workflow activity configuration."""

    def test_all_activities_have_timeout(self) -> None:
        """every activity must have a
        start_to_close_timeout."""
        tree = _parse_workflow_source()
        calls = _extract_execute_activity_kwargs(tree)
        for call in calls:
            name = call.get("_activity", "unknown")
            assert "start_to_close_timeout" in call, (
                f"{name} missing start_to_close_timeout"
            )

    def test_hash_verify_has_retry_policy(self) -> None:
        """hash verification should have a retry policy."""
        tree = _parse_workflow_source()
        calls = _extract_execute_activity_kwargs(tree)
        hash_call = calls[0]
        assert hash_call["_activity"] == "verify_asset_hash"
        assert "retry_policy" in hash_call

    def test_metadata_has_retry_policy(self) -> None:
        """metadata extraction should have a retry policy."""
        tree = _parse_workflow_source()
        calls = _extract_execute_activity_kwargs(tree)
        meta_call = calls[1]
        assert meta_call["_activity"] == "extract_asset_metadata"
        assert "retry_policy" in meta_call

    def test_proxy_gen_has_retry_policy(self) -> None:
        """proxy generation should have a retry policy."""
        tree = _parse_workflow_source()
        calls = _extract_execute_activity_kwargs(tree)
        proxy_call = calls[2]
        assert proxy_call["_activity"] == "generate_asset_proxies"
        assert "retry_policy" in proxy_call

    def test_proxy_gen_has_longest_timeout(self) -> None:
        """proxy generation should have the longest timeout
        (30 min) since it processes media."""
        src = inspect.getsource(IngestWorkflow.run)
        # proxy generation timeout is 30 minutes
        assert "minutes=30" in src

    def test_custody_and_complete_are_fast(self) -> None:
        """custody recording and mark complete should have
        short (2 min) timeouts."""
        src = inspect.getsource(IngestWorkflow.run)
        # both use minutes=2; count occurrences
        count = src.count("minutes=2")
        assert count >= 2


# ── workflow definition ───────────────────────────────────


class TestWorkflowDefinition:
    """verify workflow class structure."""

    def test_workflow_returns_asset_id(self) -> None:
        """run method should return the asset_id string."""
        sig = inspect.signature(IngestWorkflow.run)
        assert sig.return_annotation is str

    def test_workflow_accepts_single_arg(self) -> None:
        """run method takes only self and asset_id."""
        sig = inspect.signature(IngestWorkflow.run)
        params = list(sig.parameters.keys())
        assert params == ["self", "asset_id"]

    def test_all_imported_activities_are_used(self) -> None:
        """every imported activity should appear in the
        workflow source."""
        src = inspect.getsource(IngestWorkflow.run)
        expected = [
            "verify_asset_hash",
            "extract_asset_metadata",
            "generate_asset_proxies",
            "record_derivatives_custody",
            "mark_asset_complete",
        ]
        for name in expected:
            assert name in src, f"{name} not found in workflow source"
