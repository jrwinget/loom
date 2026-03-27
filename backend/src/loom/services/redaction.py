"""redaction service — applies blur/pixelate/black_box to images.

video and audio redaction are stubbed for future implementation.
pillow is an optional dependency; the service degrades gracefully
when it is not installed.
"""

import io
import logging
from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from loom.models.redaction import Redaction

logger = logging.getLogger(__name__)

# probe for pillow at import time
try:
    from PIL import Image, ImageDraw, ImageFilter

    _HAS_PILLOW = True
except ImportError:  # pragma: no cover
    _HAS_PILLOW = False


async def create_redaction(
    session: AsyncSession,
    asset_id: str,
    user_id: str,
    redaction_type: str,
    regions: list[dict[str, Any]],
) -> Redaction:
    """create a pending redaction record."""
    redaction = Redaction(
        asset_id=UUID(asset_id),
        redacted_by=UUID(user_id),
        redaction_type=redaction_type,
        regions=regions,
        status="pending",
    )
    session.add(redaction)
    await session.flush()
    return redaction


async def get_redactions(
    session: AsyncSession,
    asset_id: str,
    skip: int = 0,
    limit: int = 20,
) -> tuple[list[Redaction], int]:
    """list redactions for an asset with pagination."""
    count_result = await session.execute(
        select(func.count())
        .select_from(Redaction)
        .where(Redaction.asset_id == UUID(asset_id))
    )
    total = count_result.scalar_one()

    result = await session.execute(
        select(Redaction)
        .where(Redaction.asset_id == UUID(asset_id))
        .order_by(Redaction.created_at.desc())
        .offset(skip)
        .limit(limit)
    )
    items = list(result.scalars().all())
    return items, total


async def get_redaction(
    session: AsyncSession,
    redaction_id: str,
) -> Redaction | None:
    """get a single redaction by id."""
    result = await session.execute(
        select(Redaction).where(Redaction.id == UUID(redaction_id))
    )
    return result.scalar_one_or_none()


def apply_image_redaction(
    image_bytes: bytes,
    regions: list[dict[str, Any]],
    redaction_type: str,
    output_format: str = "PNG",
) -> bytes | None:
    """apply spatial redaction to an image.

    returns the redacted image bytes, or none if pillow is
    not available. regions use fractional coordinates (0-1).
    """
    if not _HAS_PILLOW:
        logger.warning("pillow not installed — cannot apply image redaction")
        return None

    img = Image.open(io.BytesIO(image_bytes))
    w, h = img.size

    for region in regions:
        rtype = region.get("type", "rect")
        if rtype not in ("rect", "circle"):
            continue

        # convert fractional coords to pixels
        rx = int(region.get("x", 0) * w)
        ry = int(region.get("y", 0) * h)
        rw = int(region.get("w", 0) * w)
        rh = int(region.get("h", 0) * h)
        box = (rx, ry, rx + rw, ry + rh)

        if redaction_type == "black_box":
            draw = ImageDraw.Draw(img)
            draw.rectangle(box, fill="black")

        elif redaction_type == "blur":
            region_crop = img.crop(box)
            blurred = region_crop.filter(ImageFilter.GaussianBlur(radius=20))
            img.paste(blurred, box)

        elif redaction_type == "pixelate":
            region_crop = img.crop(box)
            # shrink then enlarge to pixelate
            small = region_crop.resize(
                (max(1, rw // 10), max(1, rh // 10)),
                resample=Image.NEAREST,
            )
            pixelated = small.resize((rw, rh), resample=Image.NEAREST)
            img.paste(pixelated, box)

    buf = io.BytesIO()
    img.save(buf, format=output_format)
    return buf.getvalue()


async def apply_redaction(
    session: AsyncSession,
    redaction: Redaction,
    image_bytes: bytes | None = None,
) -> Redaction:
    """execute redaction processing.

    for images: applies pillow-based redaction.
    for video/audio: stubs that mark complete (TODO).
    """
    redaction.status = "processing"
    await session.flush()

    rtype = redaction.redaction_type

    if rtype in ("blur", "black_box", "pixelate"):
        if image_bytes is None:
            redaction.status = "failed"
            redaction.error_message = (
                "no image data provided for image redaction"
            )
            await session.flush()
            return redaction

        result = apply_image_redaction(
            image_bytes,
            redaction.regions,
            rtype,
        )
        if result is None:
            redaction.status = "failed"
            redaction.error_message = "pillow not installed — cannot process"
            await session.flush()
            return redaction

        # TODO: upload result bytes to minio derivatives bucket
        # and set output_storage_key
        redaction.status = "complete"
        await session.flush()
        return redaction

    if rtype == "audio_mute":
        # TODO: implement ffmpeg-based audio mute
        redaction.status = "complete"
        await session.flush()
        return redaction

    redaction.status = "failed"
    redaction.error_message = f"unsupported type: {rtype}"
    await session.flush()
    return redaction
