from unittest.mock import MagicMock, patch

import pytest

from loom.services.enhancement import (
    MODEL_NAME,
    EnhancementParams,
    VideoStats,
    analyze_video,
    build_filter_chain,
    enhance_image,
    enhance_video,
    enhancement_provenance,
    ffmpeg_version,
    suggest_params,
)


class TestParamValidation:
    """ranges are enforced at construction time."""

    def test_defaults_are_valid(self) -> None:
        EnhancementParams()

    @pytest.mark.parametrize(
        ("field", "value"),
        [
            ("brightness", -1.5),
            ("brightness", 1.5),
            ("contrast", -0.1),
            ("contrast", 4.1),
            ("saturation", 3.1),
            ("gamma", 0.0),
            ("gamma", 11.0),
            ("denoise", -1),
            ("denoise", 11),
            ("sharpen", 5.1),
        ],
    )
    def test_out_of_range_rejected(self, field: str, value: float) -> None:
        with pytest.raises(ValueError, match=field):
            EnhancementParams(**{field: value})

    @pytest.mark.parametrize("factor", [0, 3, 8, -2])
    def test_scale_factor_whitelist(self, factor: int) -> None:
        with pytest.raises(ValueError, match="scale_factor"):
            EnhancementParams(scale_factor=factor)


class TestFilterChain:
    """chain composition is deterministic and ordered."""

    def test_neutral_params_yield_empty_chain(self) -> None:
        assert build_filter_chain(EnhancementParams()) == ""

    def test_fixed_filter_order(self) -> None:
        params = EnhancementParams(
            brightness=0.1,
            contrast=1.2,
            denoise=4,
            sharpen=1.0,
            deinterlace=True,
            scale_factor=2,
        )
        assert build_filter_chain(params) == (
            "yadif,hqdn3d=4,eq=brightness=0.1:contrast=1.2,"
            "unsharp=5:5:1.0,scale=iw*2:ih*2:flags=lanczos"
        )

    def test_same_params_same_chain(self) -> None:
        a = EnhancementParams(gamma=1.4, denoise=2)
        b = EnhancementParams(gamma=1.4, denoise=2)
        assert build_filter_chain(a) == build_filter_chain(b)

    def test_eq_terms_omit_neutral_values(self) -> None:
        chain = build_filter_chain(EnhancementParams(saturation=0.5))
        assert chain == "eq=saturation=0.5"

    def test_deinterlace_suppressed_for_images(self) -> None:
        params = EnhancementParams(deinterlace=True)
        assert build_filter_chain(params, allow_deinterlace=False) == ""


class TestSubprocessCalls:
    """ffmpeg is invoked with the rendered chain."""

    @patch("loom.services.proxy._FFMPEG", "/usr/bin/ffmpeg")
    @patch("loom.services.proxy.subprocess.run")
    def test_enhance_video_args(self, mock_run: patch) -> None:
        enhance_video(
            "/fake/in.mp4",
            "/fake/out.mp4",
            EnhancementParams(denoise=3),
        )
        cmd = mock_run.call_args[0][0]
        assert "-vf" in cmd
        assert cmd[cmd.index("-vf") + 1] == "hqdn3d=3"
        assert cmd[cmd.index("-c:a") + 1] == "copy"
        assert cmd[-1] == "/fake/out.mp4"

    @patch("loom.services.proxy._FFMPEG", "/usr/bin/ffmpeg")
    @patch("loom.services.proxy.subprocess.run")
    def test_enhance_video_neutral_omits_vf(self, mock_run: patch) -> None:
        enhance_video("/fake/in.mp4", "/fake/out.mp4", EnhancementParams())
        assert "-vf" not in mock_run.call_args[0][0]

    @patch("loom.services.proxy._FFMPEG", "/usr/bin/ffmpeg")
    @patch("loom.services.proxy.subprocess.run")
    def test_enhance_image_ignores_deinterlace(self, mock_run: patch) -> None:
        enhance_image(
            "/fake/in.jpg",
            "/fake/out.jpg",
            EnhancementParams(deinterlace=True, sharpen=1.5),
        )
        cmd = mock_run.call_args[0][0]
        assert cmd[cmd.index("-vf") + 1] == "unsharp=5:5:1.5"


class TestProvenance:
    """generation params are complete enough to reproduce output."""

    @patch(
        "loom.services.enhancement.ffmpeg_version",
        return_value="7.1",
    )
    def test_provenance_shape(self, _mock_version: patch) -> None:
        params = EnhancementParams(denoise=2, scale_factor=2)
        prov = enhancement_provenance(params)
        assert prov["model_name"] == MODEL_NAME
        assert prov["model_version"] == "7.1"
        assert prov["model_params"]["denoise"] == 2
        assert prov["model_params"]["scale_factor"] == 2
        assert prov["model_params"]["filter_chain"] == (
            "hqdn3d=2,scale=iw*2:ih*2:flags=lanczos"
        )

    @patch("loom.services.enhancement._FFMPEG", None)
    def test_version_unknown_without_ffmpeg(self) -> None:
        assert ffmpeg_version() == "unknown"


def _stats(**overrides: object) -> VideoStats:
    """healthy-footage baseline; override per test case."""
    defaults: dict = {
        "yavg": 120.0,
        "ymin": 10.0,
        "ymax": 240.0,
        "ydif": 3.0,
        "interlaced": False,
        "height": 1080,
    }
    defaults.update(overrides)
    return VideoStats(**defaults)


class TestSuggestParams:
    """measurements map to documented, deterministic suggestions."""

    def test_healthy_footage_suggests_neutral(self) -> None:
        assert suggest_params(_stats()) == EnhancementParams()

    def test_dark_footage_suggests_brightness(self) -> None:
        params = suggest_params(_stats(yavg=50.0))
        assert params.brightness == pytest.approx(0.04)
        assert params.gamma == 1.0

    def test_very_dark_footage_adds_gamma(self) -> None:
        params = suggest_params(_stats(yavg=30.0))
        assert params.brightness > 0
        assert params.gamma == 1.4

    def test_flat_luma_suggests_contrast(self) -> None:
        params = suggest_params(_stats(ymin=80.0, ymax=150.0))
        assert params.contrast == 1.3

    def test_noisy_footage_suggests_denoise(self) -> None:
        assert suggest_params(_stats(ydif=15.0)).denoise == 4
        assert suggest_params(_stats(ydif=9.0)).denoise == 2

    def test_interlaced_footage_suggests_deinterlace(self) -> None:
        assert suggest_params(_stats(interlaced=True)).deinterlace

    def test_low_res_suggests_upscale(self) -> None:
        assert suggest_params(_stats(height=480)).scale_factor == 2

    def test_unknown_height_does_not_upscale(self) -> None:
        assert suggest_params(_stats(height=0)).scale_factor == 1

    def test_same_stats_same_suggestion(self) -> None:
        a = _stats(yavg=35.0, ydif=13.0, interlaced=True)
        b = _stats(yavg=35.0, ydif=13.0, interlaced=True)
        assert suggest_params(a) == suggest_params(b)


_FFMPEG_STDERR = """
[Parsed_metadata_2 @ 0x1] lavfi.signalstats.YMIN=16.000000
[Parsed_metadata_2 @ 0x1] lavfi.signalstats.YMAX=235.000000
[Parsed_metadata_2 @ 0x1] lavfi.signalstats.YAVG=42.500000
[Parsed_metadata_2 @ 0x1] lavfi.signalstats.YDIF=9.250000
[Parsed_metadata_2 @ 0x1] lavfi.signalstats.YMIN=18.000000
[Parsed_metadata_2 @ 0x1] lavfi.signalstats.YMAX=230.000000
[Parsed_metadata_2 @ 0x1] lavfi.signalstats.YAVG=37.500000
[Parsed_metadata_2 @ 0x1] lavfi.signalstats.YDIF=10.750000
[Parsed_idet_1 @ 0x2] Multi frame detection: TFF: 40 BFF: 10 \
Progressive: 5 Undetermined: 0
"""


class TestAnalyzeVideo:
    """stderr parsing aggregates per-frame measurements."""

    @patch("loom.services.enhancement._get_video_height")
    @patch("loom.services.enhancement._FFMPEG", "/usr/bin/ffmpeg")
    @patch("loom.services.enhancement.subprocess.run")
    def test_parses_signalstats_and_idet(
        self, mock_run: MagicMock, mock_height: MagicMock
    ) -> None:
        mock_run.return_value = MagicMock(stderr=_FFMPEG_STDERR)
        mock_height.return_value = 480

        stats = analyze_video("/fake/in.mp4")

        assert stats.yavg == pytest.approx(40.0)
        assert stats.ymin == 16.0
        assert stats.ymax == 235.0
        assert stats.ydif == pytest.approx(10.0)
        assert stats.interlaced
        assert stats.height == 480

    @patch("loom.services.enhancement._FFMPEG", "/usr/bin/ffmpeg")
    @patch("loom.services.enhancement.subprocess.run")
    def test_no_frames_raises(self, mock_run: MagicMock) -> None:
        mock_run.return_value = MagicMock(stderr="no frames here")
        with pytest.raises(ValueError, match="no measurable"):
            analyze_video("/fake/in.mp4")

    @patch("loom.services.enhancement._FFMPEG", None)
    def test_missing_ffmpeg_raises(self) -> None:
        with pytest.raises(RuntimeError, match="ffmpeg"):
            analyze_video("/fake/in.mp4")
