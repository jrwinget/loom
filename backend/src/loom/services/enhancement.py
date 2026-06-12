"""deterministic clarity-assist enhancement for video and images.

classical ffmpeg filters only — every output is reproducible from
the recorded parameters, and no filter invents content that was not
in the captured signal. ai super-resolution is excluded by policy:
it hallucinates pixels, which is indefensible for evidence (see
docs on enhancement). originals are never modified; callers store
results as derivatives with full parameter provenance.
"""

import re
import shutil
import subprocess
from dataclasses import asdict, dataclass

from loom.services.proxy import _FFMPEG, _run_ffmpeg

MODEL_NAME = "ffmpeg-deterministic-filter"

# fixed filter order: temporal cleanup first (deinterlace, denoise),
# then tonal correction (eq), then sharpening, then upscale last so
# earlier filters operate on original-resolution pixels. changing
# this order changes output, so it is part of the recorded contract.
_BRIGHTNESS_RANGE = (-1.0, 1.0)
_CONTRAST_RANGE = (0.0, 4.0)
_SATURATION_RANGE = (0.0, 3.0)
_GAMMA_RANGE = (0.1, 10.0)
_DENOISE_RANGE = (0, 10)
_SHARPEN_RANGE = (0.0, 5.0)
_SCALE_FACTORS = (1, 2, 4)


@dataclass(frozen=True)
class EnhancementParams:
    """deterministic filter parameters; defaults are all neutral."""

    brightness: float = 0.0
    contrast: float = 1.0
    saturation: float = 1.0
    gamma: float = 1.0
    denoise: int = 0
    sharpen: float = 0.0
    deinterlace: bool = False
    scale_factor: int = 1

    def __post_init__(self) -> None:
        _check_range("brightness", self.brightness, _BRIGHTNESS_RANGE)
        _check_range("contrast", self.contrast, _CONTRAST_RANGE)
        _check_range("saturation", self.saturation, _SATURATION_RANGE)
        _check_range("gamma", self.gamma, _GAMMA_RANGE)
        _check_range("denoise", self.denoise, _DENOISE_RANGE)
        _check_range("sharpen", self.sharpen, _SHARPEN_RANGE)
        if self.scale_factor not in _SCALE_FACTORS:
            msg = (
                f"scale_factor must be one of {_SCALE_FACTORS}, "
                f"got {self.scale_factor}"
            )
            raise ValueError(msg)


def _check_range(
    name: str,
    value: float,
    bounds: tuple[float, float],
) -> None:
    lo, hi = bounds
    if not lo <= value <= hi:
        msg = f"{name} must be between {lo} and {hi}, got {value}"
        raise ValueError(msg)


def build_filter_chain(
    params: EnhancementParams,
    *,
    allow_deinterlace: bool = True,
) -> str:
    """compose the ffmpeg -vf chain for the given parameters.

    pure and deterministic: identical params always produce the
    identical string. neutral parameters are omitted, so all-default
    params yield an empty chain.
    """
    filters: list[str] = []

    if params.deinterlace and allow_deinterlace:
        filters.append("yadif")

    if params.denoise > 0:
        filters.append(f"hqdn3d={params.denoise}")

    eq_terms: list[str] = []
    if params.brightness != 0.0:
        eq_terms.append(f"brightness={params.brightness}")
    if params.contrast != 1.0:
        eq_terms.append(f"contrast={params.contrast}")
    if params.saturation != 1.0:
        eq_terms.append(f"saturation={params.saturation}")
    if params.gamma != 1.0:
        eq_terms.append(f"gamma={params.gamma}")
    if eq_terms:
        filters.append("eq=" + ":".join(eq_terms))

    if params.sharpen > 0.0:
        filters.append(f"unsharp=5:5:{params.sharpen}")

    if params.scale_factor > 1:
        filters.append(
            f"scale=iw*{params.scale_factor}:ih*{params.scale_factor}"
            ":flags=lanczos"
        )

    return ",".join(filters)


def enhance_video(
    input_path: str,
    output_path: str,
    params: EnhancementParams,
) -> None:
    """write an enhanced copy of a video; the input is untouched.

    crf 18 keeps the derivative near-transparent so the enhancement,
    not the re-encode, dominates what the viewer sees. audio is
    copied bit-exact.
    """
    chain = build_filter_chain(params)
    args = ["-i", input_path]
    if chain:
        args.extend(["-vf", chain])
    args.extend(
        [
            "-c:v",
            "libx264",
            "-preset",
            "fast",
            "-crf",
            "18",
            "-c:a",
            "copy",
            output_path,
        ]
    )
    _run_ffmpeg(args)


def enhance_image(
    input_path: str,
    output_path: str,
    params: EnhancementParams,
) -> None:
    """write an enhanced copy of an image; the input is untouched.

    deinterlacing is video-only and ignored for images.
    """
    chain = build_filter_chain(params, allow_deinterlace=False)
    args = ["-i", input_path]
    if chain:
        args.extend(["-vf", chain])
    args.append(output_path)
    _run_ffmpeg(args)


def ffmpeg_version() -> str:
    """return the installed ffmpeg version string, or 'unknown'."""
    if _FFMPEG is None:
        return "unknown"
    try:
        result = subprocess.run(  # noqa: S603
            [_FFMPEG, "-version"],
            check=True,
            capture_output=True,
            text=True,
        )
    except (subprocess.CalledProcessError, OSError):
        return "unknown"
    first_line = result.stdout.splitlines()[0] if result.stdout else ""
    parts = first_line.split()
    if len(parts) >= 3 and parts[:2] == ["ffmpeg", "version"]:
        return parts[2]
    return "unknown"


@dataclass(frozen=True)
class VideoStats:
    """measured signal statistics from a sampled stretch of video."""

    yavg: float
    ymin: float
    ymax: float
    ydif: float
    interlaced: bool
    height: int


# heuristic thresholds for suggested starting parameters. these are
# starting points surfaced to the reviewer, never auto-applied; the
# human adjusts and confirms before a derivative is generated.
_DARK_YAVG = 60.0
_VERY_DARK_YAVG = 40.0
_FLAT_LUMA_RANGE = 100.0
_NOISY_YDIF = 12.0
_SLIGHTLY_NOISY_YDIF = 8.0
_LOW_RES_HEIGHT = 720

_STATS_RE = re.compile(r"lavfi\.signalstats\.(YAVG|YMIN|YMAX|YDIF)=([0-9.]+)")
_IDET_RE = re.compile(
    r"Multi frame detection:\s*TFF:\s*(\d+)\s*BFF:\s*(\d+)"
    r"\s*Progressive:\s*(\d+)"
)


def analyze_video(
    input_path: str,
    sample_seconds: float = 5.0,
) -> VideoStats:
    """measure luma statistics and interlacing on a leading sample.

    runs ffmpeg with signalstats + idet over the first
    ``sample_seconds`` and parses the per-frame metadata from
    stderr. raises RuntimeError when ffmpeg is unavailable and
    ValueError when no frames could be measured.
    """
    if _FFMPEG is None:
        msg = (
            "ffmpeg is not installed or not on PATH; "
            "clarity-assist analysis is unavailable"
        )
        raise RuntimeError(msg)

    result = subprocess.run(  # noqa: S603
        [
            _FFMPEG,
            "-hide_banner",
            "-t",
            str(sample_seconds),
            "-i",
            input_path,
            "-vf",
            "signalstats,idet,metadata=mode=print",
            "-f",
            "null",
            "-",
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    stats: dict[str, list[float]] = {
        "YAVG": [],
        "YMIN": [],
        "YMAX": [],
        "YDIF": [],
    }
    for key, value in _STATS_RE.findall(result.stderr):
        stats[key].append(float(value))
    if not stats["YAVG"]:
        msg = f"no measurable video frames in {input_path}"
        raise ValueError(msg)

    interlaced = False
    idet = _IDET_RE.search(result.stderr)
    if idet is not None:
        tff, bff, progressive = (int(g) for g in idet.groups())
        interlaced = (tff + bff) > progressive

    return VideoStats(
        yavg=sum(stats["YAVG"]) / len(stats["YAVG"]),
        ymin=min(stats["YMIN"]),
        ymax=max(stats["YMAX"]),
        ydif=sum(stats["YDIF"]) / len(stats["YDIF"]),
        interlaced=interlaced,
        height=_get_video_height(input_path),
    )


def _get_video_height(input_path: str) -> int:
    """get video stream height via ffprobe, 0 when unavailable."""
    ffprobe = shutil.which("ffprobe")
    if ffprobe is None:
        return 0
    try:
        result = subprocess.run(  # noqa: S603
            [
                ffprobe,
                "-v",
                "error",
                "-select_streams",
                "v:0",
                "-show_entries",
                "stream=height",
                "-of",
                "default=noprint_wrappers=1:nokey=1",
                input_path,
            ],
            check=True,
            capture_output=True,
            text=True,
        )
        return int(result.stdout.strip())
    except (subprocess.CalledProcessError, ValueError):
        return 0


def suggest_params(stats: VideoStats) -> EnhancementParams:
    """map measured statistics to suggested starting parameters.

    pure and deterministic: identical measurements always produce
    identical suggestions, and every suggestion is traceable to a
    documented threshold above. suggestions are a starting point
    for the reviewer, never applied without human confirmation.
    """
    brightness = 0.0
    gamma = 1.0
    if stats.yavg < _DARK_YAVG:
        brightness = round(min(0.3, (_DARK_YAVG - stats.yavg) / 255.0), 2)
        if stats.yavg < _VERY_DARK_YAVG:
            gamma = 1.4

    contrast = 1.0
    if (stats.ymax - stats.ymin) < _FLAT_LUMA_RANGE:
        contrast = 1.3

    denoise = 0
    if stats.ydif > _NOISY_YDIF:
        denoise = 4
    elif stats.ydif > _SLIGHTLY_NOISY_YDIF:
        denoise = 2

    scale_factor = 1
    if 0 < stats.height < _LOW_RES_HEIGHT:
        scale_factor = 2

    return EnhancementParams(
        brightness=brightness,
        contrast=contrast,
        gamma=gamma,
        denoise=denoise,
        deinterlace=stats.interlaced,
        scale_factor=scale_factor,
    )


def enhancement_provenance(params: EnhancementParams) -> dict[str, object]:
    """provenance dict for the derivative's generation_params column.

    records everything needed to reproduce the output byte-for-byte
    intent: tool, tool version, every parameter, and the rendered
    filter chain actually passed to ffmpeg.
    """
    return {
        "model_name": MODEL_NAME,
        "model_version": ffmpeg_version(),
        "model_params": {
            **asdict(params),
            "filter_chain": build_filter_chain(params),
        },
    }
