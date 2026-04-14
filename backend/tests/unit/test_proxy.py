from unittest.mock import patch

import pytest

from loom.services.proxy import (
    generate_image_thumbnail,
    generate_thumbnail,
    generate_thumbnails,
    generate_video_proxy,
    generate_waveform,
)


class TestProxyFunctionsExist:
    """verify proxy generation functions are callable."""

    def test_generate_video_proxy_callable(self) -> None:
        assert callable(generate_video_proxy)

    def test_generate_thumbnail_callable(self) -> None:
        assert callable(generate_thumbnail)

    def test_generate_thumbnails_callable(self) -> None:
        assert callable(generate_thumbnails)

    def test_generate_image_thumbnail_callable(
        self,
    ) -> None:
        assert callable(generate_image_thumbnail)

    def test_generate_waveform_callable(self) -> None:
        assert callable(generate_waveform)


class TestParameterValidation:
    """test parameter validation in proxy functions."""

    def test_thumbnails_count_must_be_positive(
        self,
    ) -> None:
        with pytest.raises(ValueError, match="count"):
            generate_thumbnails("/fake/in.mp4", "/fake/out", count=0)

    def test_image_thumbnail_max_width_positive(
        self,
    ) -> None:
        with pytest.raises(ValueError, match="max_width"):
            generate_image_thumbnail(
                "/fake/in.jpg",
                "/fake/out.jpg",
                max_width=0,
            )


class TestSubprocessCalls:
    """test that ffmpeg is invoked correctly."""

    @patch("loom.services.proxy._FFMPEG", "/usr/bin/ffmpeg")
    @patch("loom.services.proxy.subprocess.run")
    def test_video_proxy_calls_ffmpeg(self, mock_run: patch) -> None:
        generate_video_proxy("/in.mp4", "/out.mp4")
        mock_run.assert_called_once()
        args = mock_run.call_args[0][0]
        assert args[0] == "/usr/bin/ffmpeg"
        assert "-i" in args
        assert "/in.mp4" in args
        assert "/out.mp4" in args

    @patch("loom.services.proxy._FFMPEG", "/usr/bin/ffmpeg")
    @patch("loom.services.proxy.subprocess.run")
    def test_thumbnail_calls_ffmpeg(self, mock_run: patch) -> None:
        generate_thumbnail("/in.mp4", "/out.jpg", 5.0)
        mock_run.assert_called_once()
        args = mock_run.call_args[0][0]
        assert "-ss" in args
        assert "5.0" in args

    @patch("loom.services.proxy._FFMPEG", "/usr/bin/ffmpeg")
    @patch("loom.services.proxy.subprocess.run")
    def test_waveform_calls_ffmpeg(self, mock_run: patch) -> None:
        generate_waveform("/in.wav", "/out.png")
        mock_run.assert_called_once()
        args = mock_run.call_args[0][0]
        assert "showwavespic" in str(args)

    @patch("loom.services.proxy._FFMPEG", None)
    def test_raises_without_ffmpeg(self) -> None:
        with pytest.raises(RuntimeError, match="ffmpeg"):
            generate_video_proxy("/in.mp4", "/out.mp4")

    @patch("loom.services.proxy._FFMPEG", "/usr/bin/ffmpeg")
    @patch("loom.services.proxy.subprocess.run")
    def test_image_thumbnail_calls_ffmpeg(self, mock_run: patch) -> None:
        generate_image_thumbnail("/in.jpg", "/out.jpg", max_width=320)
        mock_run.assert_called_once()
        args = mock_run.call_args[0][0]
        assert "320:-1" in str(args)
