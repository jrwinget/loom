import logging
import shutil
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)

_FFMPEG = shutil.which("ffmpeg")


def _require_ffmpeg() -> str:
    """return ffmpeg path or raise if not found."""
    if _FFMPEG is None:
        msg = (
            "ffmpeg is not installed or not on PATH; "
            "proxy generation is unavailable"
        )
        raise RuntimeError(msg)
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
