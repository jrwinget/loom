import logging
import shutil
import subprocess
from pathlib import Path
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from loom.models.scene import Scene
from loom.services.engines import (
    REMEDY_FFMPEG,
    REMEDY_SCENEDETECT,
    EngineUnavailableError,
)
from loom.services.model_metadata import build_provenance

logger = logging.getLogger(__name__)

_FFMPEG = shutil.which("ffmpeg")
_SCENEDETECT_MODEL_NAME = "scenedetect.ContentDetector"
_SCENEDETECT_PACKAGE = "scenedetect"


def detect_scenes(
    video_path: str,
    threshold: float = 27.0,
) -> list[dict[str, Any]]:
    """use pyscenedetect to find scene boundaries.

    returns list of dicts with scene_number, start_time,
    end_time, start_frame, end_frame, duration. the single-scene
    fallback is used only when the detector RAN and found no cuts;
    a missing engine raises EngineUnavailableError instead of
    fabricating a boundary row.
    """
    try:
        from scenedetect import (
            ContentDetector,
            SceneManager,
            open_video,
        )
    except ImportError as exc:
        raise EngineUnavailableError(
            "scene_detection", REMEDY_SCENEDETECT
        ) from exc

    try:
        video = open_video(video_path)
    except Exception as exc:
        raise RuntimeError(
            f"scene detection could not open {video_path}: {exc}"
        ) from exc

    scene_manager = SceneManager()
    scene_manager.add_detector(ContentDetector(threshold=threshold))
    scene_manager.detect_scenes(video)
    scene_list = scene_manager.get_scene_list()
    provenance = build_provenance(
        _SCENEDETECT_MODEL_NAME,
        _SCENEDETECT_PACKAGE,
        {"threshold": threshold},
    )

    if not scene_list:
        return _single_scene_fallback(video_path, provenance)

    results: list[dict[str, Any]] = []
    for i, (start, end) in enumerate(scene_list):
        results.append(
            {
                "scene_number": i + 1,
                "start_time": start.get_seconds(),
                "end_time": end.get_seconds(),
                "start_frame": start.get_frames(),
                "end_frame": end.get_frames(),
                "duration": (end.get_seconds() - start.get_seconds()),
                **provenance,
            }
        )
    return results


def _single_scene_fallback(
    video_path: str,
    provenance: dict[str, Any],
) -> list[dict[str, Any]]:
    """return a single scene covering the full video.

    used only when the detector ran and found no boundaries, so the
    row carries the detector's real provenance.
    """
    duration = _get_duration(video_path)
    return [
        {
            "scene_number": 1,
            "start_time": 0.0,
            "end_time": duration,
            "start_frame": 0,
            "end_frame": 0,
            "duration": duration,
            **provenance,
        }
    ]


def _get_duration(video_path: str) -> float:
    """get video duration in seconds using ffprobe."""
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
                video_path,
            ],
            check=True,
            capture_output=True,
            text=True,
        )
        return float(result.stdout.strip())
    except (subprocess.CalledProcessError, ValueError):
        return 0.0


def generate_scene_thumbnails(
    video_path: str,
    scenes: list[dict[str, Any]],
    output_dir: str,
) -> list[str]:
    """extract a representative frame from each scene.

    uses the midpoint of each scene. returns list of
    thumbnail file paths.
    """
    if not scenes:
        return []

    if _FFMPEG is None:
        raise EngineUnavailableError("media_pipeline", REMEDY_FFMPEG)

    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    paths: list[str] = []
    for scene in scenes:
        midpoint = (scene["start_time"] + scene["end_time"]) / 2.0
        num = scene["scene_number"]
        out_file = str(out_dir / f"scene_{num:04d}.jpg")

        try:
            subprocess.run(  # noqa: S603
                [
                    _FFMPEG,
                    "-y",
                    "-hide_banner",
                    "-loglevel",
                    "error",
                    "-ss",
                    str(midpoint),
                    "-i",
                    video_path,
                    "-frames:v",
                    "1",
                    "-q:v",
                    "2",
                    out_file,
                ],
                check=True,
                capture_output=True,
            )
            paths.append(out_file)
        except subprocess.CalledProcessError as exc:
            logger.warning(
                "thumbnail extraction failed for scene %d: %s",
                num,
                exc,
            )

    return paths


async def store_scenes(
    session: AsyncSession,
    asset_id: str,
    scenes: list[dict[str, Any]],
) -> list[Scene]:
    """bulk insert scene records for an asset."""
    records: list[Scene] = []
    for scene_data in scenes:
        scene = Scene(
            asset_id=UUID(asset_id),
            scene_number=scene_data["scene_number"],
            start_time=scene_data["start_time"],
            end_time=scene_data["end_time"],
            start_frame=scene_data["start_frame"],
            end_frame=scene_data["end_frame"],
            duration=scene_data["duration"],
            thumbnail_key=scene_data.get("thumbnail_key"),
            model_name=scene_data.get("model_name"),
            model_version=scene_data.get("model_version"),
            model_params=scene_data.get("model_params"),
        )
        session.add(scene)
        records.append(scene)

    await session.flush()
    return records
