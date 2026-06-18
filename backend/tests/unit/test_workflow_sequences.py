"""lock the workflow sequences to the behaviour they replaced.

these assertions are the guardrail for the shared-spec refactor:
if a step is added, reordered, or has its retry/timeout changed,
this test changes too — and so do both execution paths that read
the spec (the temporal driver and the lite runner).
"""

from loom.workflows import sequences as seq


def _names(spec: seq.WorkflowSpec) -> list[str]:
    return [s.activity.__name__ for s in spec.steps]


def test_registry_has_every_workflow() -> None:
    assert set(seq.SPECS) == {
        "ingest",
        "url_ingest",
        "ocr",
        "transcription",
        "scene_detection",
        "export",
    }


def test_ingest_tail_order() -> None:
    assert _names(seq.INGEST) == [
        "verify_asset_hash",
        "extract_asset_metadata",
        "generate_asset_proxies",
        "record_derivatives_custody",
        "mark_asset_complete",
    ]


def test_url_ingest_is_download_then_shared_tail() -> None:
    assert _names(seq.URL_INGEST) == [
        "download_url_and_record_provenance",
        "attempt_wayback_snapshot",
        *_names(seq.INGEST),
    ]
    # the tail is the *same* objects, so the two pipelines cannot drift
    assert seq.URL_INGEST.steps[2:] == tuple(seq.INGEST.steps)


def test_ingest_retry_and_timeout_literals() -> None:
    by_name = {s.activity.__name__: s for s in seq.INGEST.steps}
    assert by_name["verify_asset_hash"].max_attempts == 3
    assert by_name["verify_asset_hash"].timeout_s == 600
    meta = by_name["extract_asset_metadata"]
    assert (meta.max_attempts, meta.initial_interval_s) == (3, 10)
    proxies = by_name["generate_asset_proxies"]
    assert proxies.max_attempts == 2
    assert proxies.heartbeat_s == 120
    assert by_name["mark_asset_complete"].max_attempts == 3


def test_ocr_store_steps_have_no_explicit_retry() -> None:
    # prepare/store had no retry_policy originally (temporal default);
    # the spec preserves that as max_attempts=None.
    by_name = {s.activity.__name__: s for s in seq.OCR.steps}
    assert by_name["prepare_ocr_input"].max_attempts is None
    assert by_name["run_ocr"].max_attempts == 2
    assert by_name["store_ocr_results"].max_attempts is None


def test_asset_status_arg_only_on_ingest_pipelines() -> None:
    assert seq.INGEST.asset_status_arg == 0
    assert seq.URL_INGEST.asset_status_arg == 0
    for name in ("ocr", "transcription", "scene_detection", "export"):
        assert seq.SPECS[name].asset_status_arg is None


def test_binders_select_the_right_args() -> None:
    download = seq.URL_INGEST.steps[0]
    assert download.bind(["asset-1", "https://x"], {}) == [
        "asset-1",
        "https://x",
    ]
    verify = seq.INGEST.steps[0]
    assert verify.bind(["asset-1"], {}) == ["asset-1"]


def test_transcription_threads_audio_path() -> None:
    steps = {s.activity.__name__: s for s in seq.TRANSCRIPTION.steps}
    assert steps["extract_audio"].key == "audio"
    transcribe = steps["transcribe_asset"]
    bound = transcribe.bind(["asset-1"], {"audio": "audio.wav"})
    assert bound == ["asset-1", "audio.wav"]
    diarize = steps["diarize_asset"]
    assert diarize.bind(["asset-1"], {"audio": "audio.wav"}) == [
        "asset-1",
        "audio.wav",
    ]
