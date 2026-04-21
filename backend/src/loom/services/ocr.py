import logging
import subprocess
import tempfile
from pathlib import Path
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from loom.models.ocr import OcrRegion
from loom.services.model_metadata import build_provenance

logger = logging.getLogger(__name__)

_TESSERACT_MODEL_NAME = "pytesseract"
_TESSERACT_PACKAGE = "pytesseract"


def extract_key_frames(
    video_path: str,
    interval_seconds: float = 5.0,
) -> list[tuple[int, float, str]]:
    """extract frames at regular intervals using ffmpeg.

    returns list of (frame_number, timestamp, image_path).
    raises ValueError if video_path does not exist.
    """
    path = Path(video_path)
    if not path.exists():
        raise ValueError(f"video not found: {video_path}")

    if interval_seconds <= 0:
        raise ValueError("interval_seconds must be positive")

    output_dir = tempfile.mkdtemp(prefix="loom_ocr_frames_")
    pattern = str(Path(output_dir) / "frame_%06d.png")

    cmd = [
        "ffmpeg",
        "-i",
        video_path,
        "-vf",
        f"fps=1/{interval_seconds}",
        "-vsync",
        "vfr",
        pattern,
    ]
    try:
        subprocess.run(  # noqa: S603
            cmd,
            capture_output=True,
            check=True,
        )
    except FileNotFoundError:
        logger.warning("ffmpeg not found, cannot extract frames")
        return []
    except subprocess.CalledProcessError as exc:
        logger.warning(
            "ffmpeg failed for %s: %s",
            video_path,
            exc.stderr,
        )
        return []

    # collect generated frames
    frames: list[tuple[int, float, str]] = []
    for i, frame_path in enumerate(
        sorted(Path(output_dir).glob("frame_*.png"))
    ):
        frame_number = i
        timestamp = i * interval_seconds
        frames.append((frame_number, timestamp, str(frame_path)))

    return frames


def run_ocr_on_image(
    image_path: str,
    language: str = "eng",
) -> list[dict[str, Any]]:
    """use pytesseract to ocr an image.

    returns list of {text, confidence, bounding_box}.
    if pytesseract not installed, returns empty with warning.
    """
    path = Path(image_path)
    if not path.exists():
        logger.warning("image not found: %s", image_path)
        return []

    try:
        import pytesseract
    except ImportError:
        logger.warning("pytesseract not installed, skipping ocr")
        return []

    try:
        from PIL import Image
    except ImportError:
        logger.warning("Pillow not installed, skipping ocr")
        return []

    try:
        img = Image.open(image_path)
        data = pytesseract.image_to_data(
            img,
            lang=language,
            output_type=pytesseract.Output.DICT,
        )
    except Exception as exc:
        logger.warning("ocr failed for %s: %s", image_path, exc)
        return []

    img_width, img_height = img.size
    regions: list[dict[str, Any]] = []
    n_boxes = len(data["text"])
    provenance = build_provenance(
        _TESSERACT_MODEL_NAME,
        _TESSERACT_PACKAGE,
        {"language": language},
    )

    for i in range(n_boxes):
        text = data["text"][i].strip()
        if not text:
            continue

        conf = float(data["conf"][i])
        if conf < 0:
            continue

        # normalize bounding box to 0-1 range
        x = data["left"][i] / img_width if img_width else 0
        y = data["top"][i] / img_height if img_height else 0
        w = data["width"][i] / img_width if img_width else 0
        h = data["height"][i] / img_height if img_height else 0

        regions.append(
            {
                "text": text,
                "confidence": conf / 100.0,
                "bounding_box": {
                    "x": round(x, 6),
                    "y": round(y, 6),
                    "width": round(w, 6),
                    "height": round(h, 6),
                },
                **provenance,
            }
        )

    return regions


def run_ocr_on_asset(
    asset_path: str,
    media_type: str,
) -> list[dict[str, Any]]:
    """orchestrate ocr for an asset.

    for images, ocr directly. for video, extract key frames
    then ocr each. for documents, attempt image conversion.
    returns list of region dicts with optional frame_number
    and timestamp fields.
    """
    path = Path(asset_path)
    if not path.exists():
        logger.warning("asset not found: %s", asset_path)
        return []

    if media_type.startswith("image"):
        regions = run_ocr_on_image(asset_path)
        # add null frame metadata for images
        for r in regions:
            r["frame_number"] = None
            r["timestamp"] = None
        return regions

    if media_type.startswith("video"):
        frames = extract_key_frames(asset_path)
        all_regions: list[dict[str, Any]] = []
        for frame_number, timestamp, frame_path in frames:
            regions = run_ocr_on_image(frame_path)
            for r in regions:
                r["frame_number"] = frame_number
                r["timestamp"] = timestamp
            all_regions.extend(regions)
        return all_regions

    # for documents (pdf, etc.), treat as image if possible
    if media_type.startswith("application"):
        logger.info(
            "document ocr not yet implemented for %s",
            media_type,
        )
        return []

    logger.warning(
        "unsupported media type for ocr: %s",
        media_type,
    )
    return []


async def store_ocr_regions(
    session: AsyncSession,
    asset_id: str,
    regions: list[dict[str, Any]],
) -> list[OcrRegion]:
    """bulk insert ocr regions into the database."""
    ocr_records: list[OcrRegion] = []
    for region in regions:
        bbox = region.get("bounding_box")
        record = OcrRegion(
            asset_id=UUID(asset_id),
            frame_number=region.get("frame_number"),
            timestamp=region.get("timestamp"),
            bounding_box=bbox,
            text=region["text"],
            confidence=region.get("confidence"),
            language=region.get("language"),
            model_name=region.get("model_name"),
            model_version=region.get("model_version"),
            model_params=region.get("model_params"),
        )
        session.add(record)
        ocr_records.append(record)

    await session.flush()
    return ocr_records
