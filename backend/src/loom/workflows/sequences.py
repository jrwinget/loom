"""single source of truth for workflow activity sequences.

each workflow is described once, as data, and consumed by both
execution paths: the temporal driver (server profile) and the
in-process lite runner (desktop profile). this prevents the two
paths from drifting — adding or reordering a step changes both.

the module is intentionally free of any temporalio import so the
lite runner can use it without pulling the workflow sandbox.
"""

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any

from loom.workflows.export_activities import build_export
from loom.workflows.ingest_activities import (
    extract_asset_metadata,
    generate_asset_proxies,
    mark_asset_complete,
    record_derivatives_custody,
    verify_asset_hash,
)
from loom.workflows.ocr_activities import (
    prepare_ocr_input,
    run_ocr,
    store_ocr_results,
)
from loom.workflows.scene_activities import (
    detect_asset_scenes,
    generate_scene_thumbs,
    store_scene_results,
)
from loom.workflows.transcription_activities import (
    diarize_asset,
    extract_audio,
    store_transcript,
    transcribe_asset,
)
from loom.workflows.url_ingest_activities import (
    attempt_wayback_snapshot,
    download_url_and_record_provenance,
)

# (workflow_args, prior_results) -> positional args for this step.
Binder = Callable[[list[Any], dict[str, Any]], list[Any]]


@dataclass(frozen=True)
class Step:
    """one activity invocation in a workflow sequence.

    ``max_attempts`` of None means "no explicit retry policy": the
    temporal driver omits the policy (server keeps the sdk default),
    while the lite runner treats it as a single attempt so a
    persistent failure can't loop forever in-process.
    """

    activity: Callable[..., Any]
    bind: Binder
    timeout_s: int
    max_attempts: int | None = None
    initial_interval_s: int | None = None
    heartbeat_s: int | None = None
    # key under which this step's return value is stored for later
    # steps' binders; defaults to the activity's name.
    result_key: str | None = None

    @property
    def key(self) -> str:
        return self.result_key or self.activity.__name__


@dataclass(frozen=True)
class WorkflowSpec:
    """an ordered activity sequence plus profile-agnostic metadata."""

    name: str
    steps: Sequence[Step]
    # index into the workflow args of the asset whose
    # processing_status this workflow owns, or None when the
    # workflow does not drive an asset's processing_status (export,
    # ocr, transcription, scene detection track their own state).
    asset_status_arg: int | None = None


# binders kept tiny and explicit; most steps just take the asset id.
def _first(args: list[Any], _results: dict[str, Any]) -> list[Any]:
    return [args[0]]


def _first_two(args: list[Any], _results: dict[str, Any]) -> list[Any]:
    return [args[0], args[1]]


def _asset_and_audio(args: list[Any], results: dict[str, Any]) -> list[Any]:
    return [args[0], results["audio"]]


# the five steps that run after bytes are on disk. defined once and
# reused by both the upload ingest and the url ingest pipelines so
# the shared tail can never drift between them.
INGEST_TAIL: tuple[Step, ...] = (
    Step(verify_asset_hash, _first, timeout_s=600, max_attempts=3),
    Step(
        extract_asset_metadata,
        _first,
        timeout_s=300,
        max_attempts=3,
        initial_interval_s=10,
    ),
    Step(
        generate_asset_proxies,
        _first,
        timeout_s=1800,
        max_attempts=2,
        initial_interval_s=60,
        heartbeat_s=120,
    ),
    Step(
        record_derivatives_custody,
        _first,
        timeout_s=120,
        max_attempts=3,
        initial_interval_s=5,
    ),
    Step(
        mark_asset_complete,
        _first,
        timeout_s=120,
        max_attempts=3,
        initial_interval_s=5,
    ),
)

INGEST = WorkflowSpec("ingest", INGEST_TAIL, asset_status_arg=0)

URL_INGEST = WorkflowSpec(
    "url_ingest",
    (
        Step(
            download_url_and_record_provenance,
            _first_two,
            timeout_s=1800,
            max_attempts=3,
        ),
        Step(
            attempt_wayback_snapshot,
            _first_two,
            timeout_s=60,
            max_attempts=1,
        ),
        *INGEST_TAIL,
    ),
    asset_status_arg=0,
)

OCR = WorkflowSpec(
    "ocr",
    (
        Step(prepare_ocr_input, _first, timeout_s=1800),
        Step(run_ocr, _first, timeout_s=3600, max_attempts=2),
        Step(store_ocr_results, _first, timeout_s=300),
    ),
)

TRANSCRIPTION = WorkflowSpec(
    "transcription",
    (
        Step(
            extract_audio,
            _first,
            timeout_s=1800,
            max_attempts=2,
            result_key="audio",
        ),
        Step(
            transcribe_asset,
            _asset_and_audio,
            timeout_s=7200,
            max_attempts=2,
        ),
        Step(
            diarize_asset,
            _asset_and_audio,
            timeout_s=3600,
            max_attempts=1,
        ),
        Step(store_transcript, _first, timeout_s=300),
    ),
)

SCENE_DETECTION = WorkflowSpec(
    "scene_detection",
    (
        Step(detect_asset_scenes, _first, timeout_s=1800, max_attempts=2),
        Step(generate_scene_thumbs, _first, timeout_s=900),
        Step(store_scene_results, _first, timeout_s=300),
    ),
)

EXPORT = WorkflowSpec(
    "export",
    (Step(build_export, _first, timeout_s=3600, max_attempts=2),),
)

SPECS: dict[str, WorkflowSpec] = {
    spec.name: spec
    for spec in (
        INGEST,
        URL_INGEST,
        OCR,
        TRANSCRIPTION,
        SCENE_DETECTION,
        EXPORT,
    )
}
