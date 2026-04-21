"""detect clock drift across evidence-file time sources.

each device (phone, body cam, dashcam) records timestamps in
multiple places: exif/container metadata, the filesystem filename,
sometimes an overlay burned into the frame. these may disagree
because devices are mis-set, time-zone-aware code is imperfect, or
the file was copied through tools that rewrite creation dates.

this module compares whatever sources are available and computes a
single clock_confidence score in [0.0, 1.0]:

    1.0  = all sources agree within a few seconds (high confidence)
    0.5  = partial agreement (two of three sources close)
    0.1  = strong disagreement (>5 minutes)
    None = fewer than two sources to compare

clock_offset_seconds is NOT computed here — automatic detection
cannot know which source is "correct". offset is set only when a
user asserts a reference anchor via the clock-anchor endpoint.

per the issue-39 spec, this is deliberately conservative: surface
disagreement, never silently pick a winner.
"""

import re
from collections.abc import Iterable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from loom.models.asset import Asset
from loom.models.chain_of_custody import ChainOfCustodyEntry

# filename timestamp patterns, ordered most-specific first.
# each produces a (match, strptime_format) pair; the group-join
# step below concatenates captured groups and parses once.
_FILENAME_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    # IMG_20260420_120000 / VID_20260420_120000 / PXL_20260420_120000
    (
        re.compile(
            r"(?:IMG|VID|MOV|PXL|DSC|DJI)[_-]?(\d{8})[_T-]?(\d{6})",
            re.IGNORECASE,
        ),
        "%Y%m%d%H%M%S",
    ),
    # 2026-04-20_12-00-00  or  2026-04-20T12:00:00
    (
        re.compile(
            r"(\d{4})[-_](\d{2})[-_](\d{2})"
            r"[T_\s-](\d{2})[-:_](\d{2})[-:_](\d{2})"
        ),
        "%Y%m%d%H%M%S",
    ),
    # 20260420_120000 / 20260420T120000 / 20260420-120000
    (
        re.compile(r"(\d{8})[T_-](\d{6})"),
        "%Y%m%d%H%M%S",
    ),
)

# thresholds tuned for device-clock drift, not latency;
# frame-overlay timestamps have second-level precision so <2s
# is essentially "agree" for evidence purposes.
_AGREE_THRESHOLD_S = 2.0
_PARTIAL_THRESHOLD_S = 300.0  # 5 minutes

CONFIDENCE_AGREE = 1.0
CONFIDENCE_PARTIAL = 0.5
CONFIDENCE_DISAGREE = 0.1


def parse_filename_timestamp(filename: str) -> datetime | None:
    """extract a UTC-naive datetime from a filename, or None.

    filename may be a full path; only the basename is scanned.
    returns timezone-aware UTC datetime; naive input from a
    filename is treated as UTC (we have no better signal).
    """
    stem = Path(filename).stem
    for pattern, fmt in _FILENAME_PATTERNS:
        match = pattern.search(stem)
        if match is None:
            continue
        try:
            joined = "".join(match.groups())
            return datetime.strptime(joined, fmt).replace(tzinfo=UTC)
        except ValueError:
            continue
    return None


def parse_metadata_timestamp(value: Any) -> datetime | None:
    """parse a time string from container/exif metadata, or None.

    accepts common iso-like shapes emitted by ffmpeg/pyav
    (e.g. "2026-04-20T12:00:00.000000Z"). returns timezone-aware
    UTC. returns None if the value is unusable.
    """
    if not isinstance(value, str) or not value.strip():
        return None
    raw = value.strip().replace("Z", "+00:00")
    # strip fractional seconds beyond 6 digits (some encoders)
    raw = re.sub(r"(\.\d{6})\d+", r"\1", raw)
    try:
        dt = datetime.fromisoformat(raw)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


def _max_pairwise_delta(
    timestamps: Iterable[datetime],
) -> float:
    """largest pairwise absolute difference in seconds."""
    items = list(timestamps)
    max_delta = 0.0
    for i in range(len(items)):
        for j in range(i + 1, len(items)):
            delta = abs((items[i] - items[j]).total_seconds())
            if delta > max_delta:
                max_delta = delta
    return max_delta


def detect_clock_drift(
    filename: str,
    raw_metadata: dict[str, Any] | None,
) -> dict[str, Any]:
    """compare available time sources and return a drift report.

    returns a dict with keys:
        confidence: float | None  (0.0-1.0 or None if < 2 sources)
        sources:    dict[str, str | None]  — iso strings, per source
        max_delta_seconds: float | None

    intended to be written back onto Asset.clock_confidence
    verbatim; the sources dict is stored in asset.metadata_extracted
    so reviewers can audit the inputs without re-running extraction.
    """
    raw_metadata = raw_metadata or {}
    sources: dict[str, datetime | None] = {
        "container": parse_metadata_timestamp(
            raw_metadata.get("capture_time_utc")
        ),
        "exif": parse_metadata_timestamp(
            raw_metadata.get("exif_datetime_original")
        ),
        "filename": parse_filename_timestamp(filename),
    }

    available = [t for t in sources.values() if t is not None]
    max_delta: float | None
    confidence: float | None

    if len(available) < 2:
        max_delta = None
        confidence = None
    else:
        max_delta = _max_pairwise_delta(available)
        if max_delta <= _AGREE_THRESHOLD_S:
            confidence = CONFIDENCE_AGREE
        elif max_delta <= _PARTIAL_THRESHOLD_S:
            confidence = CONFIDENCE_PARTIAL
        else:
            confidence = CONFIDENCE_DISAGREE

    return {
        "confidence": confidence,
        "max_delta_seconds": max_delta,
        "sources": {
            name: (dt.isoformat() if dt is not None else None)
            for name, dt in sources.items()
        },
    }


async def apply_clock_anchor(
    session: AsyncSession,
    asset_id: str,
    *,
    reported_time: datetime,
    actual_time: datetime,
    actor_id: str,
    note: str | None = None,
    ip_address: str | None = None,
) -> Asset:
    """record a user-asserted clock correction.

    offset is actual - reported: positive means the device clock
    was running behind. writes an append-only chain-of-custody
    entry and raises its clock_confidence to 1.0 (human-verified
    beats anything auto-detection could conclude).
    """
    result = await session.execute(
        select(Asset).where(Asset.id == UUID(asset_id))
    )
    asset = result.scalar_one_or_none()
    if asset is None:
        msg = f"asset {asset_id} not found"
        raise ValueError(msg)

    # normalize to UTC before subtracting — clients may send either
    # timezone-aware or naive (treated as UTC) values.
    reported_utc = _to_utc(reported_time)
    actual_utc = _to_utc(actual_time)
    offset = (actual_utc - reported_utc).total_seconds()

    asset.clock_offset_seconds = offset
    asset.clock_confidence = CONFIDENCE_AGREE

    entry = ChainOfCustodyEntry(
        asset_id=UUID(asset_id),
        action="clock_anchor_corrected",
        actor_id=UUID(actor_id),
        detail={
            "reported_time": reported_utc.isoformat(),
            "actual_time": actual_utc.isoformat(),
            "offset_seconds": offset,
            "note": note,
        },
        ip_address=ip_address,
    )
    session.add(entry)
    await session.flush()
    return asset


def _to_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)
