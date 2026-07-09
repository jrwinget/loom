from unittest.mock import patch

from loom.services.engines import (
    REMEDY_WHISPER,
    EngineUnavailableError,
    probe_engines,
)


class TestEngineUnavailableError:
    def test_carries_engine_and_remedy(self) -> None:
        exc = EngineUnavailableError("transcription", REMEDY_WHISPER)
        assert exc.engine == "transcription"
        assert exc.remedy == REMEDY_WHISPER
        assert "transcription unavailable" in str(exc)

    def test_is_a_runtime_error(self) -> None:
        # callers that only know RuntimeError still catch it
        assert issubclass(EngineUnavailableError, RuntimeError)


class TestProbeEngines:
    def test_reports_all_engines(self) -> None:
        result = probe_engines()
        assert set(result.keys()) == {
            "transcription_local",
            "ocr",
            "scene_detection",
            "media_pipeline",
            "diarization",
        }

    def test_missing_import_reports_remedy(self) -> None:
        with patch(
            "loom.services.engines.importlib.util.find_spec",
            return_value=None,
        ):
            result = probe_engines()
        assert result["transcription_local"].status == "missing"
        assert result["transcription_local"].remedy == REMEDY_WHISPER

    def test_missing_binary_reports_missing(self) -> None:
        with patch(
            "loom.services.engines.shutil.which",
            return_value=None,
        ):
            result = probe_engines()
        assert result["media_pipeline"].status == "missing"
        assert result["media_pipeline"].remedy is not None
