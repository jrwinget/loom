import array
import math
import shutil
import subprocess
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from loom.services.engines import EngineUnavailableError
from loom.services.proxy import (
    generate_image_thumbnail,
    generate_thumbnail,
    generate_thumbnails,
    generate_video_proxy,
    generate_waveform,
    generate_waveform_peaks,
)


def _pcm_s16le(samples: list[int]) -> bytes:
    """pack signed 16-bit samples as little-endian pcm bytes."""
    buf = array.array("h", samples)
    if array.array("h", [1]).tobytes()[0] != 1:
        buf.byteswap()  # normalize to little-endian on big-endian hosts
    return buf.tobytes()


def _sine_pcm(count: int, amplitude: int, rate: int = 8000) -> list[int]:
    """a pure tone at 440 hz — a real, non-flat envelope."""
    return [
        int(amplitude * math.sin(2 * math.pi * 440 * n / rate))
        for n in range(count)
    ]


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


class TestWaveformPeaks:
    """the peaks are the real signal envelope, never a synthetic shape."""

    def test_count_must_be_positive(self) -> None:
        with pytest.raises(ValueError, match="count"):
            generate_waveform_peaks("/in.wav", count=0)

    @patch("loom.services.proxy._FFMPEG", None)
    def test_raises_engine_unavailable_without_ffmpeg(self) -> None:
        # never fabricate a shape when the decoder is missing
        with pytest.raises(EngineUnavailableError, match="ffmpeg"):
            generate_waveform_peaks("/in.wav")

    @patch("loom.services.proxy._FFMPEG", "/usr/bin/ffmpeg")
    @patch("loom.services.proxy.subprocess.run")
    def test_returns_requested_count_of_floats_in_unit_range(
        self, mock_run: Mock
    ) -> None:
        pcm = _pcm_s16le(_sine_pcm(8000, amplitude=30000))
        mock_run.return_value = Mock(stdout=pcm)

        peaks = generate_waveform_peaks("/in.wav", count=200)

        assert len(peaks) == 200
        assert all(0.0 <= p <= 1.0 for p in peaks)
        # peak-normalized: the loudest bucket reaches full height
        assert max(peaks) == pytest.approx(1.0)

    @patch("loom.services.proxy._FFMPEG", "/usr/bin/ffmpeg")
    @patch("loom.services.proxy.subprocess.run")
    def test_peaks_track_a_loud_then_quiet_signal(self, mock_run: Mock) -> None:
        # a synthetic sin() bar chart could not reproduce this: the
        # envelope must fall because the real amplitude falls
        loud = _sine_pcm(4000, amplitude=30000)
        quiet = _sine_pcm(4000, amplitude=800)
        mock_run.return_value = Mock(stdout=_pcm_s16le(loud + quiet))

        peaks = generate_waveform_peaks("/in.wav", count=100)

        assert peaks[0] > peaks[-1]
        assert peaks[-1] < 0.1

    @patch("loom.services.proxy._FFMPEG", "/usr/bin/ffmpeg")
    @patch("loom.services.proxy.subprocess.run")
    def test_silence_returns_all_zero_peaks(self, mock_run: Mock) -> None:
        mock_run.return_value = Mock(stdout=_pcm_s16le([0] * 8000))

        peaks = generate_waveform_peaks("/in.wav", count=64)

        assert peaks == [0.0] * 64

    @pytest.mark.skipif(
        shutil.which("ffmpeg") is None, reason="ffmpeg not installed"
    )
    def test_real_ffmpeg_decode_of_a_generated_tone(
        self, tmp_path: Path
    ) -> None:
        # end-to-end against the actual decoder when it is present
        ffmpeg = shutil.which("ffmpeg")
        assert ffmpeg is not None
        wav = tmp_path / "tone.wav"
        subprocess.run(  # noqa: S603
            [
                ffmpeg,
                "-y",
                "-hide_banner",
                "-loglevel",
                "error",
                "-f",
                "lavfi",
                "-i",
                "sine=frequency=440:duration=1",
                str(wav),
            ],
            check=True,
            capture_output=True,
        )

        peaks = generate_waveform_peaks(str(wav), count=300)

        assert len(peaks) == 300
        assert all(0.0 <= p <= 1.0 for p in peaks)
        assert max(peaks) == pytest.approx(1.0)
