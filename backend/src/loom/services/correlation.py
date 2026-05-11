"""multi-perspective correlation of assets covering the same event.

given a case full of evidence from different devices and angles,
this module proposes groupings: "these N files likely capture the
same moment." it fuses independent signals into a single confidence
score and always surfaces which signals agreed vs disagreed so a
reviewer can audit the call.

signals, in priority order:

    temporal  — do effective capture windows overlap? weighted by
                clock_confidence from issue #39's drift detection.
    geo       — how close were the devices? linear fall-off between
                near_meters (1.0) and far_meters (0.0).
    audio     — FUTURE: chromaprint / acoustic fingerprint match.
                hook emitted in reasoning as {score: None, ...}.
    visual    — FUTURE: shared-scene detection via frame features.
                hook emitted in reasoning as {score: None, ...}.

temporal is a hard gate: pairs whose windows do not overlap (even
within tolerance) are not correlated. geo lifts or suppresses an
otherwise-temporal match but cannot create one on its own.

per the issue-40 spec, this is deliberately never auto-merging. a
candidate is written with status='pending' and a human resolves it
via decide_candidate. no face recognition, no identity resolution.
"""

from datetime import UTC, datetime
from math import asin, cos, radians, sin, sqrt
from statistics import mean
from typing import Any, Protocol, TypeGuard
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from loom.models.asset import Asset
from loom.models.base import _generate_uuid7
from loom.models.correlation import (
    CorrelationCandidate,
    CorrelationCandidateMember,
)


class _AssetWithGeo(Protocol):
    """narrowing protocol for assets with non-null lat/lon."""

    capture_location_lat: float
    capture_location_lon: float

# hard cap on per-case scan size. fuse_pair_signals is O(n^2) and a
# case with 500 assets is 124,750 pairs; capping at 200 (19,900 pairs)
# keeps scans responsive without losing realistic case sizes. raise via
# ValueError so the api layer can surface a 422 and a batch caller can
# decide whether to chunk.
MAX_ASSETS_PER_SCAN = 200

# photos have no duration; treat them as a 1-second window so an
# instantaneous capture still has an interval to overlap against.
_PHOTO_WINDOW_SECONDS = 1.0

# tolerance for "windows overlap" — devices that report identical
# event times routinely disagree by a few seconds at millisecond
# precision, and trimming to <5s costs more true positives than
# it saves false ones.
_DEFAULT_OVERLAP_TOLERANCE_S = 5.0

# geo thresholds in meters. near: same scene from a few steps away.
# far: same block but different event. between: linear fall-off.
_DEFAULT_NEAR_METERS = 50.0
_DEFAULT_FAR_METERS = 1000.0

# temporal-confidence fallbacks when clock_confidence is missing.
_TEMPORAL_CONF_BOTH_UNKNOWN = 0.3
_TEMPORAL_CONF_ONE_UNKNOWN = 0.5

# fusion weights — temporal dominates because it gates; geo is a
# modifier. audio/visual are placeholders with weight 0 today.
_WEIGHT_TEMPORAL = 0.6
_WEIGHT_GEO = 0.4

_EARTH_RADIUS_METERS = 6_371_000.0

_VALID_STATUSES = frozenset({"pending", "accepted", "rejected"})
_TERMINAL_STATUSES = frozenset({"accepted", "rejected"})


def asset_effective_window(
    asset: Asset,
) -> tuple[datetime, datetime] | None:
    """return [effective_start, effective_end] in UTC, or None.

    applies asset.clock_offset_seconds (positive = device clock was
    behind). pulls duration from metadata_extracted['duration_seconds']
    when present; otherwise uses a 1-second window so still photos
    can participate in overlap arithmetic.
    """
    if asset.capture_time is None:
        return None

    start = _to_utc(asset.capture_time)
    if asset.clock_offset_seconds:
        start = datetime.fromtimestamp(
            start.timestamp() + asset.clock_offset_seconds,
            tz=UTC,
        )

    duration = _extract_duration_seconds(asset.metadata_extracted)
    if duration is None or duration <= 0:
        duration = _PHOTO_WINDOW_SECONDS

    end = datetime.fromtimestamp(start.timestamp() + duration, tz=UTC)
    return start, end


def windows_overlap(
    a: tuple[datetime, datetime],
    b: tuple[datetime, datetime],
    tolerance_seconds: float = _DEFAULT_OVERLAP_TOLERANCE_S,
) -> bool:
    """True if two time windows overlap within tolerance."""
    a_start, a_end = a
    b_start, b_end = b
    latest_start = max(a_start, b_start)
    earliest_end = min(a_end, b_end)
    gap = (latest_start - earliest_end).total_seconds()
    return gap <= tolerance_seconds


def haversine_meters(
    lat1: float,
    lon1: float,
    lat2: float,
    lon2: float,
) -> float:
    """great-circle distance between two points on Earth, in meters."""
    phi1 = radians(lat1)
    phi2 = radians(lat2)
    dphi = radians(lat2 - lat1)
    dlambda = radians(lon2 - lon1)
    a = sin(dphi / 2) ** 2 + cos(phi1) * cos(phi2) * sin(dlambda / 2) ** 2
    c = 2 * asin(sqrt(a))
    return _EARTH_RADIUS_METERS * c


def geo_proximity_score(
    a: Asset,
    b: Asset,
    near_meters: float = _DEFAULT_NEAR_METERS,
    far_meters: float = _DEFAULT_FAR_METERS,
) -> float | None:
    """1.0 within near_meters, 0.0 beyond far_meters, linear between.

    returns None if either asset lacks lat or lon. same-location
    devices score 1.0; devices >far_meters apart score 0.0 even
    though they may still correlate temporally.
    """
    if not _has_geo(a) or not _has_geo(b):
        return None

    distance = haversine_meters(
        a.capture_location_lat,
        a.capture_location_lon,
        b.capture_location_lat,
        b.capture_location_lon,
    )
    if distance <= near_meters:
        return 1.0
    if distance >= far_meters:
        return 0.0
    span = far_meters - near_meters
    return float(1.0 - (distance - near_meters) / span)


def temporal_confidence(a: Asset, b: Asset) -> float:
    """weight a temporal match by the clock confidence of both sides.

    conservative: the pair is only as trustworthy as its weakest
    clock, so we take the minimum of the available values. if one
    clock is unknown fall back to 0.5, if both unknown fall back
    to 0.3 — a temporal match is still evidence but weaker.
    """
    ca = a.clock_confidence
    cb = b.clock_confidence
    if ca is not None and cb is not None:
        return float(min(ca, cb))
    if ca is not None:
        return float(min(ca, _TEMPORAL_CONF_ONE_UNKNOWN))
    if cb is not None:
        return float(min(cb, _TEMPORAL_CONF_ONE_UNKNOWN))
    return _TEMPORAL_CONF_BOTH_UNKNOWN


def fuse_pair_signals(
    a: Asset,
    b: Asset,
) -> tuple[float, dict[str, Any]] | None:
    """fuse per-signal scores into (confidence, reasoning).

    returns None when the pair cannot be correlated: either asset
    lacks capture_time, or their effective windows do not overlap
    within tolerance. otherwise returns a confidence in [0, 1] and
    a reasoning dict with per-signal score+notes entries. audio and
    visual entries are stubs with score=None for the MVP.
    """
    window_a = asset_effective_window(a)
    window_b = asset_effective_window(b)
    if window_a is None or window_b is None:
        return None
    if not windows_overlap(window_a, window_b):
        return None

    temporal_score = temporal_confidence(a, b)
    temporal_block: dict[str, Any] = {
        "score": temporal_score,
        "notes": (
            f"overlap {_format_overlap_seconds(window_a, window_b)}s; "
            f"min clock_confidence {temporal_score:.2f}"
        ),
    }

    geo_score = geo_proximity_score(a, b)
    geo_block: dict[str, Any] | None
    if geo_score is None:
        geo_block = {
            "score": None,
            "notes": "one or both assets missing lat/lon",
        }
    else:
        distance = haversine_meters(
            a.capture_location_lat or 0.0,
            a.capture_location_lon or 0.0,
            b.capture_location_lat or 0.0,
            b.capture_location_lon or 0.0,
        )
        geo_block = {
            "score": geo_score,
            "notes": f"distance ~{distance:.0f}m",
        }

    reasoning: dict[str, Any] = {
        "temporal": temporal_block,
        "geo": geo_block,
        "audio": {"score": None, "notes": "not computed (mvp)"},
        "visual": {"score": None, "notes": "not computed (mvp)"},
    }

    confidence = _combine_weighted(temporal_score, geo_score)
    return confidence, reasoning


async def compute_correlation_candidates(
    session: AsyncSession,
    case_id: str,
) -> list[dict[str, Any]]:
    """find correlation candidates among all assets in a case.

    queries every asset in the case, fuses every pair of signals,
    groups overlapping pairs by connected component. each component
    with >=2 members becomes a candidate dict shaped like:

        {
            "asset_ids": [...],
            "start_utc": datetime,
            "end_utc":   datetime,
            "confidence": float,   # mean of contained pair scores
            "reasoning":  {...},   # per-pair breakdown
        }
    """
    result = await session.execute(
        select(Asset).where(Asset.case_id == UUID(case_id))
    )
    assets = list(result.scalars().all())
    if len(assets) < 2:
        return []
    if len(assets) > MAX_ASSETS_PER_SCAN:
        raise ValueError(
            f"case has {len(assets)} assets; correlation scan is "
            f"capped at {MAX_ASSETS_PER_SCAN} per run. split the "
            "case or run scans on subsets."
        )

    pair_meta = _build_pair_meta(assets)
    if not pair_meta:
        return []

    components = _connected_components(list(pair_meta.keys()))
    asset_by_id = {str(asset.id): asset for asset in assets}
    candidates: list[dict[str, Any]] = []
    for component in components:
        candidate = _component_to_candidate(component, asset_by_id, pair_meta)
        if candidate is not None:
            candidates.append(candidate)
    return candidates


def _build_pair_meta(
    assets: list[Asset],
) -> dict[tuple[str, str], dict[str, Any]]:
    """fuse every pair; keep only the pairs that correlate."""
    asset_ids = [str(asset.id) for asset in assets]
    pair_meta: dict[tuple[str, str], dict[str, Any]] = {}
    for i in range(len(assets)):
        for j in range(i + 1, len(assets)):
            fused = fuse_pair_signals(assets[i], assets[j])
            if fused is None:
                continue
            confidence, reasoning = fused
            key = _pair_key(asset_ids[i], asset_ids[j])
            pair_meta[key] = {
                "confidence": confidence,
                "reasoning": reasoning,
            }
    return pair_meta


def _component_to_candidate(
    component: set[str],
    asset_by_id: dict[str, Asset],
    pair_meta: dict[tuple[str, str], dict[str, Any]],
) -> dict[str, Any] | None:
    """turn a connected component into a candidate dict, or None."""
    if len(component) < 2:
        return None

    member_ids = sorted(component)
    windows = [
        window
        for asset_id in member_ids
        if (window := asset_effective_window(asset_by_id[asset_id])) is not None
    ]
    if not windows:
        return None

    pair_scores: list[float] = []
    pair_reasoning: dict[str, dict[str, Any]] = {}
    for idx_a in range(len(member_ids)):
        for idx_b in range(idx_a + 1, len(member_ids)):
            key = _pair_key(member_ids[idx_a], member_ids[idx_b])
            meta = pair_meta.get(key)
            if meta is None:
                continue
            pair_scores.append(meta["confidence"])
            pair_reasoning[f"{key[0]}::{key[1]}"] = meta["reasoning"]

    if not pair_scores:
        return None

    return {
        "asset_ids": member_ids,
        "start_utc": min(w[0] for w in windows),
        "end_utc": max(w[1] for w in windows),
        "confidence": float(mean(pair_scores)),
        "reasoning": {
            "pairs": pair_reasoning,
            "aggregation": "mean_of_pair_confidences",
        },
    }


async def persist_correlation_candidates(
    session: AsyncSession,
    case_id: str,
    candidates: list[dict[str, Any]],
) -> list[CorrelationCandidate]:
    """replace pending candidates for case with the given list.

    existing accepted/rejected candidates are preserved. caller is
    responsible for commit. ids are assigned python-side via uuid7
    so candidate + member rows can be staged in a single flush.
    """
    case_uuid = UUID(case_id)
    existing = await session.execute(
        select(CorrelationCandidate).where(
            CorrelationCandidate.case_id == case_uuid,
            CorrelationCandidate.status == "pending",
        )
    )
    for stale in existing.scalars().all():
        await session.delete(stale)

    created: list[CorrelationCandidate] = []
    for candidate in candidates:
        row = CorrelationCandidate(
            id=_generate_uuid7(),
            case_id=case_uuid,
            start_utc=candidate["start_utc"],
            end_utc=candidate["end_utc"],
            confidence=float(candidate["confidence"]),
            reasoning=candidate["reasoning"],
            status="pending",
        )
        session.add(row)
        for asset_id in candidate["asset_ids"]:
            session.add(
                CorrelationCandidateMember(
                    candidate_id=row.id,
                    asset_id=UUID(asset_id),
                )
            )
        created.append(row)

    await session.flush()
    return created


async def decide_candidate(
    session: AsyncSession,
    candidate_id: str,
    user_id: str,
    new_status: str,
) -> CorrelationCandidate:
    """accept or reject a pending candidate.

    idempotent: re-asserting the current terminal status is a
    no-op and returns the row unchanged. changing an already-
    decided candidate to a different status is rejected.
    """
    if new_status not in _TERMINAL_STATUSES:
        msg = (
            f"invalid status {new_status!r}; "
            f"expected one of {sorted(_TERMINAL_STATUSES)}"
        )
        raise ValueError(msg)

    result = await session.execute(
        select(CorrelationCandidate).where(
            CorrelationCandidate.id == UUID(candidate_id),
        )
    )
    candidate = result.scalar_one_or_none()
    if candidate is None:
        msg = f"correlation candidate {candidate_id} not found"
        raise ValueError(msg)

    if candidate.status == new_status:
        return candidate

    if candidate.status in _TERMINAL_STATUSES:
        msg = (
            f"candidate {candidate_id} already decided "
            f"({candidate.status}); cannot change to {new_status}"
        )
        raise ValueError(msg)

    candidate.status = new_status
    candidate.decided_by = UUID(user_id)
    candidate.decided_at = datetime.now(UTC)
    await session.flush()
    return candidate


async def list_candidates(
    session: AsyncSession,
    case_id: str,
    status: str | None = None,
) -> list[CorrelationCandidate]:
    """fetch candidates for a case, optionally filtered by status.

    members are loaded in a companion query and stitched on each
    row as `.members` so api layers can serialize without lazy-
    loading against a closed session.
    """
    if status is not None and status not in _VALID_STATUSES:
        msg = (
            f"invalid status {status!r}; "
            f"expected one of {sorted(_VALID_STATUSES)}"
        )
        raise ValueError(msg)

    stmt = select(CorrelationCandidate).where(
        CorrelationCandidate.case_id == UUID(case_id),
    )
    if status is not None:
        stmt = stmt.where(CorrelationCandidate.status == status)
    stmt = stmt.order_by(CorrelationCandidate.start_utc)

    result = await session.execute(stmt)
    candidates = list(result.scalars().all())
    if not candidates:
        return []

    member_result = await session.execute(
        select(CorrelationCandidateMember).where(
            CorrelationCandidateMember.candidate_id.in_(
                [c.id for c in candidates]
            ),
        )
    )
    members_by_candidate: dict[UUID, list[CorrelationCandidateMember]] = {}
    for member in member_result.scalars().all():
        members_by_candidate.setdefault(member.candidate_id, []).append(member)
    for candidate in candidates:
        candidate.members = members_by_candidate.get(  # type: ignore[attr-defined]
            candidate.id, []
        )
    return candidates


def _extract_duration_seconds(metadata: Any) -> float | None:
    """read duration_seconds from extracted metadata, defensively."""
    if not isinstance(metadata, dict):
        return None
    value = metadata.get("duration_seconds")
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _format_overlap_seconds(
    a: tuple[datetime, datetime],
    b: tuple[datetime, datetime],
) -> str:
    """human-readable overlap magnitude for reasoning notes."""
    latest_start = max(a[0], b[0])
    earliest_end = min(a[1], b[1])
    overlap = (earliest_end - latest_start).total_seconds()
    return f"{overlap:.1f}"


def _has_geo(asset: Asset) -> TypeGuard[_AssetWithGeo]:
    return (
        asset.capture_location_lat is not None
        and asset.capture_location_lon is not None
    )


def _combine_weighted(
    temporal_score: float,
    geo_score: float | None,
) -> float:
    """weighted mean of available signals.

    when geo is unknown, temporal carries the full weight; we do
    not penalize an otherwise-strong temporal match just because
    one side lacks gps.
    """
    if geo_score is None:
        return _clamp01(temporal_score)
    numerator = _WEIGHT_TEMPORAL * temporal_score + _WEIGHT_GEO * geo_score
    denominator = _WEIGHT_TEMPORAL + _WEIGHT_GEO
    return _clamp01(numerator / denominator)


def _clamp01(value: float) -> float:
    if value < 0.0:
        return 0.0
    if value > 1.0:
        return 1.0
    return value


def _pair_key(a: str, b: str) -> tuple[str, str]:
    """canonicalize an undirected edge so lookups are order-free."""
    return (a, b) if a <= b else (b, a)


def _to_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _connected_components(
    pairs: list[tuple[str, str]],
) -> list[set[str]]:
    """build connected components from string edge pairs.

    wraps graph_utils.connected_components, which operates on
    integer indices.
    """
    from loom.services.graph_utils import (
        connected_components as _cc,
    )

    nodes: list[str] = []
    node_idx: dict[str, int] = {}
    for a, b in pairs:
        for x in (a, b):
            if x not in node_idx:
                node_idx[x] = len(nodes)
                nodes.append(x)

    int_pairs = [(node_idx[a], node_idx[b]) for a, b in pairs]
    components = _cc(int_pairs, len(nodes))
    return [{nodes[i] for i in comp} for comp in components]
