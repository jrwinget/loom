import logging
from itertools import combinations
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from loom.models.asset import Asset
from loom.models.duplicate import (
    DuplicateCluster,
    DuplicateClusterMember,
)

logger = logging.getLogger(__name__)


def compute_phash(image_path: str) -> str:
    """compute perceptual hash of an image using average hash.

    resizes to 8x8 grayscale, computes mean, generates 64-bit
    hash as 16-char hex string. falls back to empty string if
    PIL is unavailable.
    """
    try:
        from PIL import Image
    except ImportError:
        logger.warning("PIL not available; skipping phash computation")
        return ""

    try:
        img = Image.open(image_path).convert("L").resize((8, 8))
    except Exception:
        logger.warning("failed to open image: %s", image_path)
        return ""

    pixels = list(img.getdata())
    mean_val = sum(pixels) / len(pixels)
    bits = 0
    for px in pixels:
        bits = (bits << 1) | (1 if px >= mean_val else 0)
    return f"{bits:016x}"


def compute_video_phash(video_path: str) -> str:
    """extract midpoint frame from video and compute its phash.

    uses ffmpeg via subprocess to extract a single frame, then
    delegates to compute_phash. returns empty string on failure.
    """
    import subprocess
    import tempfile
    from pathlib import Path

    try:
        # probe duration
        result = subprocess.run(  # noqa: S603
            [  # noqa: S607
                "ffprobe",
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-of",
                "default=noprint_wrappers=1:nokey=1",
                video_path,
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )
        duration = float(result.stdout.strip())
        midpoint = duration / 2.0
    except Exception:
        logger.warning("failed to probe video duration: %s", video_path)
        return ""

    with tempfile.TemporaryDirectory() as tmpdir:
        frame_path = str(Path(tmpdir) / "frame.png")
        try:
            subprocess.run(  # noqa: S603
                [  # noqa: S607
                    "ffmpeg",
                    "-ss",
                    str(midpoint),
                    "-i",
                    video_path,
                    "-frames:v",
                    "1",
                    "-y",
                    frame_path,
                ],
                capture_output=True,
                timeout=30,
                check=True,
            )
        except Exception:
            logger.warning("failed to extract frame from: %s", video_path)
            return ""

        return compute_phash(frame_path)


def hamming_distance(hash1: str, hash2: str) -> int:
    """compute hamming distance between two hex hash strings."""
    if not hash1 or not hash2:
        return 64  # max distance for 64-bit hash
    val1 = int(hash1, 16)
    val2 = int(hash2, 16)
    xor = val1 ^ val2
    return bin(xor).count("1")


def _find_exact_duplicates(
    assets: list[Asset],
) -> list[dict[str, Any]]:
    """group assets with identical sha256 hashes."""
    hash_groups: dict[str, list[Asset]] = {}
    for asset in assets:
        hash_groups.setdefault(asset.sha256_hash, []).append(asset)

    clusters: list[dict[str, Any]] = []
    for _sha256, group in hash_groups.items():
        if len(group) >= 2:
            clusters.append(
                {
                    "type": "exact",
                    "asset_ids": [str(a.id) for a in group],
                    "phashes": {str(a.id): "" for a in group},
                }
            )
    return clusters


async def _load_phash_map(
    session: AsyncSession,
    assets: list[Asset],
) -> dict[str, str]:
    """load existing phashes for image/video assets."""
    image_assets = [a for a in assets if a.media_type in ("image", "video")]
    phash_map: dict[str, str] = {}
    for asset in image_assets:
        member_result = await session.execute(
            select(DuplicateClusterMember.phash).where(
                DuplicateClusterMember.asset_id == asset.id,
                DuplicateClusterMember.phash.isnot(None),
            )
        )
        existing = member_result.scalar_one_or_none()
        if existing:
            phash_map[str(asset.id)] = existing
    return phash_map


def _find_near_duplicate_clusters(
    phash_map: dict[str, str],
    existing_clusters: list[dict[str, Any]],
    threshold: int,
) -> list[dict[str, Any]]:
    """find near-duplicate clusters from phash comparisons."""
    phash_ids = list(phash_map.keys())
    near_dup_pairs: list[tuple[str, str]] = []
    for id1, id2 in combinations(phash_ids, 2):
        dist = hamming_distance(phash_map[id1], phash_map[id2])
        if dist <= threshold:
            near_dup_pairs.append((id1, id2))

    if not near_dup_pairs:
        return []

    # collect ids already in exact-match clusters
    exact_ids: set[str] = set()
    for c in existing_clusters:
        exact_ids.update(c["asset_ids"])

    clusters: list[dict[str, Any]] = []
    components = _connected_components(near_dup_pairs)
    for component in components:
        if not component - exact_ids:
            continue
        clusters.append(
            {
                "type": "near",
                "asset_ids": list(component),
                "phashes": {aid: phash_map.get(aid, "") for aid in component},
            }
        )
    return clusters


async def find_duplicates(
    session: AsyncSession,
    case_id: str,
    threshold: int = 10,
) -> list[dict[str, Any]]:
    """find duplicate clusters among assets in a case.

    queries all assets, compares phashes stored on cluster
    members (or sha256 for exact matches), groups those within
    hamming distance threshold. returns list of cluster dicts.
    """
    result = await session.execute(
        select(Asset).where(
            Asset.case_id == UUID(case_id),
        )
    )
    assets = list(result.scalars().all())

    if len(assets) < 2:
        return []

    clusters = _find_exact_duplicates(assets)
    phash_map = await _load_phash_map(session, assets)
    near_clusters = _find_near_duplicate_clusters(
        phash_map, clusters, threshold
    )
    clusters.extend(near_clusters)

    return clusters


def _connected_components(
    pairs: list[tuple[str, str]],
) -> list[set[str]]:
    """build connected components from edge pairs."""
    parent: dict[str, str] = {}

    def find(x: str) -> str:
        while parent.get(x, x) != x:
            parent[x] = parent.get(parent[x], parent[x])
            x = parent[x]
        return x

    def union(a: str, b: str) -> None:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[ra] = rb

    for a, b in pairs:
        parent.setdefault(a, a)
        parent.setdefault(b, b)
        union(a, b)

    groups: dict[str, set[str]] = {}
    for node in parent:
        root = find(node)
        groups.setdefault(root, set()).add(node)

    return list(groups.values())


async def create_cluster(
    session: AsyncSession,
    case_id: str,
    asset_ids: list[str],
    phashes: dict[str, str],
) -> DuplicateCluster:
    """create a duplicate cluster with members."""
    cluster = DuplicateCluster(
        case_id=UUID(case_id),
        status="pending",
    )
    session.add(cluster)
    await session.flush()

    # compute distances relative to first member's phash
    ref_phash = ""
    for aid in asset_ids:
        if phashes.get(aid):
            ref_phash = phashes[aid]
            break

    for i, aid in enumerate(asset_ids):
        ph = phashes.get(aid, "")
        dist = (
            float(hamming_distance(ref_phash, ph)) if ref_phash and ph else None
        )
        member = DuplicateClusterMember(
            cluster_id=cluster.id,
            asset_id=UUID(aid),
            phash=ph or None,
            distance=dist,
            is_primary=(i == 0),
        )
        session.add(member)

    await session.flush()
    return cluster


async def update_cluster_status(
    session: AsyncSession,
    cluster_id: str,
    status: str,
) -> DuplicateCluster:
    """update the review status of a cluster."""
    result = await session.execute(
        select(DuplicateCluster).where(
            DuplicateCluster.id == UUID(cluster_id),
        )
    )
    cluster = result.scalar_one()
    cluster.status = status
    await session.flush()
    return cluster


async def set_primary_member(
    session: AsyncSession,
    cluster_id: str,
    asset_id: str,
) -> None:
    """set one member as primary, unset all others."""
    result = await session.execute(
        select(DuplicateClusterMember).where(
            DuplicateClusterMember.cluster_id == UUID(cluster_id),
        )
    )
    members = list(result.scalars().all())
    for member in members:
        member.is_primary = str(member.asset_id) == asset_id
    await session.flush()
