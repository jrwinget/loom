import tempfile
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID

from loom.services.scene_detection import (
    detect_scenes,
    generate_scene_thumbnails,
    store_scenes,
)


class TestDetectScenes:
    """tests for detect_scenes."""

    def test_missing_scenedetect_returns_fallback(self) -> None:
        """gracefully returns single scene when lib missing."""
        with patch.dict("sys.modules", {"scenedetect": None}):
            result = detect_scenes("/fake/video.mp4")
        assert len(result) == 1
        assert result[0]["scene_number"] == 1
        assert result[0]["start_time"] == 0.0

    def test_fallback_has_required_keys(self) -> None:
        """fallback scene dict has all expected keys."""
        with patch.dict("sys.modules", {"scenedetect": None}):
            result = detect_scenes("/fake/video.mp4")
        scene = result[0]
        expected_keys = {
            "scene_number",
            "start_time",
            "end_time",
            "start_frame",
            "end_frame",
            "duration",
        }
        assert set(scene.keys()) == expected_keys

    def test_successful_detection(self) -> None:
        """returns scene list from scenedetect."""
        # mock the scenedetect module
        mock_start = MagicMock()
        mock_start.get_seconds.return_value = 0.0
        mock_start.get_frames.return_value = 0

        mock_mid = MagicMock()
        mock_mid.get_seconds.return_value = 5.0
        mock_mid.get_frames.return_value = 150

        mock_end = MagicMock()
        mock_end.get_seconds.return_value = 10.0
        mock_end.get_frames.return_value = 300

        mock_scene_manager = MagicMock()
        mock_scene_manager.get_scene_list.return_value = [
            (mock_start, mock_mid),
            (mock_mid, mock_end),
        ]

        mock_sd = MagicMock()
        mock_sd.SceneManager.return_value = mock_scene_manager
        mock_sd.ContentDetector.return_value = MagicMock()
        mock_sd.open_video.return_value = MagicMock()

        with patch.dict("sys.modules", {"scenedetect": mock_sd}):
            result = detect_scenes("/fake/video.mp4")

        assert len(result) == 2
        assert result[0]["scene_number"] == 1
        assert result[0]["start_time"] == 0.0
        assert result[0]["end_time"] == 5.0
        assert result[1]["scene_number"] == 2
        assert result[1]["start_time"] == 5.0

    def test_open_video_failure_returns_fallback(self) -> None:
        """returns fallback when video cannot be opened."""
        mock_sd = MagicMock()
        mock_sd.open_video.side_effect = RuntimeError("bad file")

        with patch.dict("sys.modules", {"scenedetect": mock_sd}):
            result = detect_scenes("/fake/video.mp4")

        assert len(result) == 1
        assert result[0]["scene_number"] == 1


class TestGenerateSceneThumbnails:
    """tests for generate_scene_thumbnails."""

    def test_empty_scenes_returns_empty(self) -> None:
        """no scenes means no thumbnails."""
        with tempfile.TemporaryDirectory() as tmpdir:
            result = generate_scene_thumbnails("/fake/video.mp4", [], tmpdir)
        assert result == []

    def test_no_ffmpeg_returns_empty(self) -> None:
        """gracefully returns empty when ffmpeg missing."""
        scenes = [
            {
                "scene_number": 1,
                "start_time": 0.0,
                "end_time": 5.0,
            }
        ]
        with (
            tempfile.TemporaryDirectory() as tmpdir,
            patch(
                "loom.services.scene_detection._FFMPEG",
                None,
            ),
        ):
            result = generate_scene_thumbnails(
                "/fake/video.mp4", scenes, tmpdir
            )
        assert result == []

    def test_generates_thumbnails(self) -> None:
        """creates thumbnail files via ffmpeg subprocess."""
        scenes = [
            {
                "scene_number": 1,
                "start_time": 0.0,
                "end_time": 10.0,
            },
            {
                "scene_number": 2,
                "start_time": 10.0,
                "end_time": 20.0,
            },
        ]
        with (
            tempfile.TemporaryDirectory() as tmpdir,
            patch(
                "loom.services.scene_detection._FFMPEG",
                "/usr/bin/ffmpeg",
            ),
            patch("loom.services.scene_detection.subprocess.run") as mock_run,
        ):
            result = generate_scene_thumbnails(
                "/fake/video.mp4", scenes, tmpdir
            )
            assert len(result) == 2
            assert mock_run.call_count == 2
            # verify midpoint timestamps used
            first_call_args = mock_run.call_args_list[0]
            cmd = first_call_args[0][0]
            # midpoint of scene 1: (0+10)/2 = 5.0
            assert "5.0" in cmd

    def test_subprocess_failure_skips_scene(self) -> None:
        """failed ffmpeg call skips that thumbnail."""
        import subprocess

        scenes = [
            {
                "scene_number": 1,
                "start_time": 0.0,
                "end_time": 10.0,
            }
        ]
        with (
            tempfile.TemporaryDirectory() as tmpdir,
            patch(
                "loom.services.scene_detection._FFMPEG",
                "/usr/bin/ffmpeg",
            ),
            patch(
                "loom.services.scene_detection.subprocess.run",
                side_effect=subprocess.CalledProcessError(1, "ffmpeg"),
            ),
        ):
            result = generate_scene_thumbnails(
                "/fake/video.mp4", scenes, tmpdir
            )
            assert result == []


class TestStoreScenes:
    """tests for store_scenes."""

    async def test_creates_records(self) -> None:
        """bulk inserts scene records into session."""
        session = AsyncMock()
        scenes = [
            {
                "scene_number": 1,
                "start_time": 0.0,
                "end_time": 5.0,
                "start_frame": 0,
                "end_frame": 150,
                "duration": 5.0,
            },
            {
                "scene_number": 2,
                "start_time": 5.0,
                "end_time": 10.0,
                "start_frame": 150,
                "end_frame": 300,
                "duration": 5.0,
            },
        ]
        asset_id = "01912345-6789-7abc-8def-012345678903"

        result = await store_scenes(session, asset_id, scenes)

        assert len(result) == 2
        assert session.add.call_count == 2
        assert session.flush.called
        assert result[0].scene_number == 1
        assert result[1].scene_number == 2
        assert result[0].asset_id == UUID(asset_id)

    async def test_empty_scenes_returns_empty(self) -> None:
        """no scenes to insert returns empty list."""
        session = AsyncMock()
        result = await store_scenes(session, "some-id", [])
        assert result == []
        assert session.add.call_count == 0

    async def test_thumbnail_key_stored(self) -> None:
        """thumbnail_key is persisted when provided."""
        session = AsyncMock()
        scenes = [
            {
                "scene_number": 1,
                "start_time": 0.0,
                "end_time": 5.0,
                "start_frame": 0,
                "end_frame": 150,
                "duration": 5.0,
                "thumbnail_key": "thumbs/scene_0001.jpg",
            }
        ]
        asset_id = "01912345-6789-7abc-8def-012345678903"

        result = await store_scenes(session, asset_id, scenes)
        assert result[0].thumbnail_key == ("thumbs/scene_0001.jpg")
