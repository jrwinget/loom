import logging
import mimetypes
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def extract_metadata_from_file(file_path: str) -> dict[str, Any]:
    """attempts to extract metadata from a file.

    uses pyav for video/audio files, basic info for others.
    returns a dict with normalized fields.
    """
    path = Path(file_path)
    if not path.exists():
        return {
            "error": f"file not found: {file_path}",
            "raw": {},
            "normalized": normalize_metadata({}),
        }

    mime_type, _ = mimetypes.guess_type(file_path)
    mime_type = mime_type or "application/octet-stream"

    # try pyav for video/audio
    if mime_type.startswith(("video/", "audio/")):
        return _extract_av_metadata(file_path, mime_type)

    # basic metadata for everything else
    stat = path.stat()
    raw: dict[str, Any] = {
        "file_size_bytes": stat.st_size,
        "file_type_detected": mime_type,
    }
    return {
        "error": None,
        "raw": raw,
        "normalized": normalize_metadata(raw),
    }


def _extract_av_metadata(file_path: str, mime_type: str) -> dict[str, Any]:
    """extract metadata using pyav for audio/video files."""
    try:
        import av
    except ImportError:
        return {
            "error": "pyav not installed",
            "raw": {},
            "normalized": normalize_metadata({}),
        }

    raw: dict[str, Any] = {"file_type_detected": mime_type}
    try:
        container = av.open(file_path)
    except Exception as exc:
        logger.warning("av.open failed for %s: %s", file_path, exc)
        return {
            "error": str(exc),
            "raw": raw,
            "normalized": normalize_metadata(raw),
        }

    try:
        # container-level info
        if container.duration is not None:
            raw["duration_seconds"] = float(container.duration / av.time_base)

        # video streams
        video_streams = container.streams.video
        if video_streams:
            vs = video_streams[0]
            raw["width"] = vs.codec_context.width
            raw["height"] = vs.codec_context.height
            raw["codec_video"] = vs.codec_context.name
            if vs.average_rate is not None:
                raw["frame_rate"] = float(vs.average_rate)

        # audio streams
        audio_streams = container.streams.audio
        if audio_streams:
            aus = audio_streams[0]
            raw["codec_audio"] = aus.codec_context.name

        # try to get capture time from metadata
        if container.metadata:
            for key in (
                "creation_time",
                "date",
                "com.apple.quicktime.creationdate",
            ):
                if key in container.metadata:
                    raw["capture_time_utc"] = container.metadata[key]
                    break
    finally:
        container.close()

    return {
        "error": None,
        "raw": raw,
        "normalized": normalize_metadata(raw),
    }


def normalize_metadata(raw: dict[str, Any]) -> dict[str, Any]:
    """extracts normalized fields from raw metadata.

    all fields are nullable; returns a dict with a fixed
    set of keys.
    """
    return {
        "duration_seconds": raw.get("duration_seconds"),
        "width": raw.get("width"),
        "height": raw.get("height"),
        "frame_rate": raw.get("frame_rate"),
        "codec_video": raw.get("codec_video"),
        "codec_audio": raw.get("codec_audio"),
        "capture_time_utc": raw.get("capture_time_utc"),
        "file_type_detected": raw.get("file_type_detected"),
    }
