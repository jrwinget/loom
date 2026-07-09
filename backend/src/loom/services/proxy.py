import array
import logging
import shutil
import subprocess
import sys
from pathlib import Path

from loom.services.engines import (
    REMEDY_FFMPEG,
    EngineUnavailableError,
)

logger = logging.getLogger(__name__)

_FFMPEG = shutil.which("ffmpeg")

# real audio-envelope config. the peaks are decoded from the actual
# signal — never a synthesized stand-in — so a fabricated waveform
# can't pass as evidence.
WAVEFORM_PEAKS_VERSION = 1
WAVEFORM_PEAKS_METHOD = "ffmpeg-pcm-s16le-max-abs-peak-normalized"
_PEAKS_COUNT = 800
_PEAKS_SAMPLE_RATE = 8000
_PCM_FULL_SCALE = 32768.0


def _require_ffmpeg() -> str:
    """return ffmpeg path or raise if not found."""
    if _FFMPEG is None:
        raise EngineUnavailableError("media_pipeline", REMEDY_FFMPEG)
    return _FFMPEG


def _run_ffmpeg(args: list[str]) -> None:
    """run ffmpeg subprocess with standard flags."""
    ffmpeg = _require_ffmpeg()
    cmd = [ffmpeg, "-y", "-hide_banner", "-loglevel", "error"]
    cmd.extend(args)
    subprocess.run(  # noqa: S603
        cmd, check=True, capture_output=True
    )


def _get_duration(input_path: str) -> float:
    """get duration in seconds using ffprobe."""
    ffprobe = shutil.which("ffprobe")
    if ffprobe is None:
        return 0.0
    try:
        result = subprocess.run(  # noqa: S603
            [
                ffprobe,
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-of",
                "default=noprint_wrappers=1:nokey=1",
                input_path,
            ],
            check=True,
            capture_output=True,
            text=True,
        )
        return float(result.stdout.strip())
    except (subprocess.CalledProcessError, ValueError):
        return 0.0


def generate_video_proxy(input_path: str, output_path: str) -> None:
    """transcode to 720p h.264 proxy using ffmpeg."""
    _run_ffmpeg(
        [
            "-i",
            input_path,
            "-vf",
            "scale=-2:720",
            "-c:v",
            "libx264",
            "-preset",
            "fast",
            "-crf",
            "23",
            "-c:a",
            "aac",
            "-b:a",
            "128k",
            output_path,
        ]
    )


def generate_thumbnail(
    input_path: str,
    output_path: str,
    timestamp: float = 0.0,
) -> None:
    """extract single frame at timestamp as jpeg."""
    _run_ffmpeg(
        [
            "-ss",
            str(timestamp),
            "-i",
            input_path,
            "-frames:v",
            "1",
            "-q:v",
            "2",
            output_path,
        ]
    )


def generate_thumbnails(
    input_path: str,
    output_dir: str,
    count: int = 5,
) -> list[str]:
    """extract frames at evenly spaced intervals.

    returns list of output file paths.
    """
    if count < 1:
        msg = "count must be >= 1"
        raise ValueError(msg)

    duration = _get_duration(input_path)
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    paths: list[str] = []
    for i in range(count):
        ts = 0.0 if count == 1 else (i / (count - 1)) * duration
        out_file = str(out_dir / f"thumb_{i:03d}.jpg")
        generate_thumbnail(input_path, out_file, ts)
        paths.append(out_file)

    return paths


def generate_image_thumbnail(
    input_path: str,
    output_path: str,
    max_width: int = 320,
) -> None:
    """resize an image to max_width using ffmpeg."""
    if max_width < 1:
        msg = "max_width must be >= 1"
        raise ValueError(msg)
    _run_ffmpeg(
        [
            "-i",
            input_path,
            "-vf",
            f"scale={max_width}:-1",
            output_path,
        ]
    )


def generate_waveform(input_path: str, output_path: str) -> None:
    """generate a waveform image from an audio file."""
    _run_ffmpeg(
        [
            "-i",
            input_path,
            "-filter_complex",
            "showwavespic=s=640x120:colors=white",
            "-frames:v",
            "1",
            output_path,
        ]
    )


def generate_waveform_peaks(
    input_path: str,
    count: int = _PEAKS_COUNT,
) -> list[float]:
    """extract ``count`` normalized peak magnitudes in [0, 1].

    decodes the audio down to mono 16-bit pcm via ffmpeg, buckets the
    samples into ``count`` slices, and takes the max absolute amplitude
    per slice normalized to the loudest peak. these values are the real
    signal envelope, so a missing ffmpeg raises rather than fabricating
    a shape the reviewer would mistake for the recording.
    """
    if count < 1:
        msg = "count must be >= 1"
        raise ValueError(msg)

    ffmpeg = _require_ffmpeg()
    result = subprocess.run(  # noqa: S603
        [
            ffmpeg,
            "-hide_banner",
            "-loglevel",
            "error",
            "-i",
            input_path,
            "-ac",
            "1",
            "-ar",
            str(_PEAKS_SAMPLE_RATE),
            "-f",
            "s16le",
            "-",
        ],
        check=True,
        capture_output=True,
    )

    pcm = result.stdout
    # each sample is a 2-byte signed short; drop a dangling odd byte
    usable = len(pcm) - (len(pcm) % 2)
    samples: array.array[int] = array.array("h")
    samples.frombytes(pcm[:usable])
    if sys.byteorder != "little":
        # ffmpeg emits little-endian; match it on big-endian hosts
        samples.byteswap()

    return _downsample_peaks(samples, count)


def _downsample_peaks(
    samples: "array.array[int]",
    count: int,
) -> list[float]:
    """bucket samples into ``count`` max-abs peaks, normalized to [0, 1]."""
    total = len(samples)
    if total == 0:
        return [0.0] * count

    raw: list[float] = []
    for i in range(count):
        start = (i * total) // count
        end = ((i + 1) * total) // count
        if end <= start:
            raw.append(0.0)
            continue
        segment = samples[start:end]
        peak = max(max(segment), -min(segment))
        raw.append(peak / _PCM_FULL_SCALE)

    loudest = max(raw)
    if loudest <= 0:
        return raw
    return [round(p / loudest, 4) for p in raw]
