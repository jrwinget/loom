import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

from loom.services.metadata import (
    extract_metadata_from_file,
    normalize_metadata,
)


class TestNormalizeMetadata:
    """tests for normalize_metadata."""

    def test_empty_dict_returns_all_none(self) -> None:
        result = normalize_metadata({})
        assert result == {
            "duration_seconds": None,
            "width": None,
            "height": None,
            "frame_rate": None,
            "codec_video": None,
            "codec_audio": None,
            "capture_time_utc": None,
            "file_type_detected": None,
        }

    def test_extracts_known_fields(self) -> None:
        raw = {
            "duration_seconds": 120.5,
            "width": 1920,
            "height": 1080,
            "frame_rate": 29.97,
            "codec_video": "h264",
            "codec_audio": "aac",
            "capture_time_utc": "2024-01-01T00:00:00Z",
            "file_type_detected": "video/mp4",
        }
        result = normalize_metadata(raw)
        assert result["duration_seconds"] == 120.5
        assert result["width"] == 1920
        assert result["height"] == 1080
        assert result["frame_rate"] == 29.97
        assert result["codec_video"] == "h264"
        assert result["codec_audio"] == "aac"
        assert result["file_type_detected"] == "video/mp4"

    def test_ignores_unknown_fields(self) -> None:
        raw = {
            "width": 640,
            "some_random_field": "ignored",
        }
        result = normalize_metadata(raw)
        assert result["width"] == 640
        assert "some_random_field" not in result

    def test_partial_fields(self) -> None:
        raw = {"codec_audio": "mp3"}
        result = normalize_metadata(raw)
        assert result["codec_audio"] == "mp3"
        assert result["width"] is None
        assert result["duration_seconds"] is None


class TestExtractMetadataFromFile:
    """tests for extract_metadata_from_file."""

    def test_missing_file_returns_error(self) -> None:
        result = extract_metadata_from_file("/nonexistent/file.mp4")
        assert result["error"] is not None
        assert "not found" in result["error"]
        assert result["normalized"] is not None

    def test_non_av_file_returns_basic_info(self) -> None:
        with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as f:
            f.write(b"hello world")
            f.flush()
            path = f.name

        try:
            result = extract_metadata_from_file(path)
            assert result["error"] is None
            assert result["raw"]["file_size_bytes"] == 11
            assert result["normalized"]["file_type_detected"] is not None
        finally:
            Path(path).unlink(missing_ok=True)

    def test_av_import_failure_handled(self) -> None:
        """if pyav is not installed, return graceful error."""
        with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as f:
            f.write(b"\x00" * 100)
            f.flush()
            path = f.name

        try:
            with patch("loom.services.metadata.mimetypes") as mock_mt:
                mock_mt.guess_type.return_value = (
                    "video/mp4",
                    None,
                )
                # patch av import to raise ImportError
                with patch.dict("sys.modules", {"av": None}):
                    result = extract_metadata_from_file(path)
                    assert result["error"] is not None
        finally:
            Path(path).unlink(missing_ok=True)

    def test_av_open_failure_handled(self) -> None:
        """if av.open() raises, return error gracefully."""
        with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as f:
            f.write(b"\x00" * 100)
            f.flush()
            path = f.name

        try:
            mock_av = MagicMock()
            mock_av.open.side_effect = RuntimeError("bad file")
            mock_av.time_base = 1000000
            with (
                patch.dict("sys.modules", {"av": mock_av}),
                patch("loom.services.metadata.mimetypes") as mock_mt,
            ):
                mock_mt.guess_type.return_value = (
                    "video/mp4",
                    None,
                )
                result = extract_metadata_from_file(path)
                assert result["error"] is not None
                assert "bad file" in result["error"]
        finally:
            Path(path).unlink(missing_ok=True)

    def test_successful_av_extraction(self) -> None:
        """test successful metadata extraction with mock av."""
        with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as f:
            f.write(b"\x00" * 100)
            f.flush()
            path = f.name

        try:
            # build mock av module and container
            mock_codec_ctx = MagicMock()
            mock_codec_ctx.width = 1920
            mock_codec_ctx.height = 1080
            mock_codec_ctx.name = "h264"

            mock_video_stream = MagicMock()
            mock_video_stream.codec_context = mock_codec_ctx
            mock_video_stream.average_rate = 30.0

            mock_audio_codec = MagicMock()
            mock_audio_codec.name = "aac"
            mock_audio_stream = MagicMock()
            mock_audio_stream.codec_context = mock_audio_codec

            mock_container = MagicMock()
            mock_container.duration = 60000000
            mock_container.streams.video = [mock_video_stream]
            mock_container.streams.audio = [mock_audio_stream]
            mock_container.metadata = {"creation_time": "2024-06-15T12:00:00Z"}

            mock_av = MagicMock()
            mock_av.open.return_value = mock_container
            mock_av.time_base = 1000000

            with (
                patch.dict("sys.modules", {"av": mock_av}),
                patch("loom.services.metadata.mimetypes") as mock_mt,
            ):
                mock_mt.guess_type.return_value = (
                    "video/mp4",
                    None,
                )
                result = extract_metadata_from_file(path)

            assert result["error"] is None
            norm = result["normalized"]
            assert norm["width"] == 1920
            assert norm["height"] == 1080
            assert norm["codec_video"] == "h264"
            assert norm["codec_audio"] == "aac"
            assert norm["capture_time_utc"] == "2024-06-15T12:00:00Z"
        finally:
            Path(path).unlink(missing_ok=True)
