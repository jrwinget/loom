import logging
import shutil
import subprocess
from pathlib import Path
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from loom.models.scene import Scene

logger = logging.getLogger(__name__)

_FFMPEG = shutil.which("ffmpeg")


def detect_scenes(
    video_path: str,
    threshold: float = 27.0,
) -> list[dict]:
    """use pyscenedetect to find scene boundaries.

    returns list of dicts with scene_number, start_time,
    end_time, start_frame, end_frame, duration.

    if scenedetect is not installed, returns a single-scene
    fallback covering the entire video.
    """
    try:
        from scenedetect import (
            ContentDetector,
            SceneManager,
            open_video,
        )
    except ImportError:
        logger.warning(
            "scenedetect not installed; returning single-scene fallback for %s",
            video_path,
        )
        return _single_scene_fallback(video_path)

    try:
        video = open_video(video_path)
    except Exception as exc:
        logger.warning(
            "failed to open video %s: %s",
            video_path,
            exc,
        )
        return _single_scene_fallback(video_path)

    scene_manager = SceneManager()
    scene_manager.add_detector(ContentDetector(threshold=threshold))
    scene_manager.detect_scenes(video)
    scene_list = scene_manager.get_scene_list()

    if not scene_list:
        return _single_scene_fallback(video_path)

    results: list[dict] = []
    for i, (start, end) in enumerate(scene_list):
        results.append(
            {
                "scene_number": i + 1,
                "start_time": start.get_seconds(),
                "end_time": end.get_seconds(),
                "start_frame": start.get_frames(),
                "end_frame": end.get_frames(),
                "duration": (end.get_seconds() - start.get_seconds()),
            }
        )
    return results


def _single_scene_fallback(video_path: str) -> list[dict]:
    """return a single scene covering the full video."""
    duration = _get_duration(video_path)
    return [
        {
            "scene_number": 1,
            "start_time": 0.0,
            "end_time": duration,
            "start_frame": 0,
            "end_frame": 0,
            "duration": duration,
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
    scenes: list[dict],
    output_dir: str,
) -> list[str]:
    """extract a representative frame from each scene.

    uses the midpoint of each scene. returns list of
    thumbnail file paths.
    """
    if not scenes:
        return []

    if _FFMPEG is None:
        logger.warning("ffmpeg not found; cannot generate thumbnails")
        return []

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
    scenes: list[dict],
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
        )
        session.add(scene)
        records.append(scene)

    await session.flush()
    return records
