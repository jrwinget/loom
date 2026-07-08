"""engine availability probing and failure typing.

silent degradation is banned for evidence processing: a job that
cannot run because an engine is missing must fail with a message
that tells the operator how to fix the install, not fabricate an
empty or placeholder result. the probe feeds the capabilities
endpoint so the ui can disable actions up front.
"""

import importlib.util
import shutil
import subprocess
from dataclasses import dataclass

REMEDY_FFMPEG = (
    "this install is missing ffmpeg — reinstall Loom, or install "
    "ffmpeg and make sure it is on PATH"
)
REMEDY_WHISPER = (
    "on-device transcription is not installed — use cloud "
    "transcription (Settings → AI) or install the ai extra"
)
REMEDY_TESSERACT = (
    "OCR is not installed — install the ai extra and the tesseract binary"
)
REMEDY_SCENEDETECT = "scene detection is not installed — install the ai extra"
REMEDY_DIARIZATION = "speaker diarization runs on the server profile only"


class EngineUnavailableError(RuntimeError):
    """a processing engine is not installed or not usable.

    ``remedy`` is user-facing: it tells the operator what to do,
    not what went wrong internally.
    """

    def __init__(self, engine: str, remedy: str) -> None:
        super().__init__(f"{engine} unavailable: {remedy}")
        self.engine = engine
        self.remedy = remedy


@dataclass(frozen=True)
class EngineStatus:
    status: str  # "available" | "missing"
    remedy: str | None = None
    version: str | None = None


def _probe_import(module: str, remedy: str) -> EngineStatus:
    if importlib.util.find_spec(module) is not None:
        return EngineStatus(status="available")
    return EngineStatus(status="missing", remedy=remedy)


def _probe_binary(binary: str, remedy: str) -> EngineStatus:
    path = shutil.which(binary)
    if path is None:
        return EngineStatus(status="missing", remedy=remedy)
    try:
        out = subprocess.run(  # noqa: S603
            [path, "-version"],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        first = (out.stdout or out.stderr).splitlines()
        version = first[0].strip() if first else None
    except Exception:
        version = None
    return EngineStatus(status="available", version=version)


def probe_engines() -> dict[str, EngineStatus]:
    """inventory the processing engines this install can actually run."""
    return {
        "transcription_local": _probe_import("faster_whisper", REMEDY_WHISPER),
        "ocr": _probe_ocr(),
        "scene_detection": _probe_import("scenedetect", REMEDY_SCENEDETECT),
        "media_pipeline": _probe_binary("ffmpeg", REMEDY_FFMPEG),
        "diarization": _probe_import("pyannote.audio", REMEDY_DIARIZATION),
    }


def _probe_ocr() -> EngineStatus:
    # pytesseract is a thin wrapper; the binary does the work
    if importlib.util.find_spec("pytesseract") is None:
        return EngineStatus(status="missing", remedy=REMEDY_TESSERACT)
    if shutil.which("tesseract") is None:
        return EngineStatus(status="missing", remedy=REMEDY_TESSERACT)
    return EngineStatus(status="available")
