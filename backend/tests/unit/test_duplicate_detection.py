from unittest.mock import (
    AsyncMock,
    MagicMock,
    patch,
)

from loom.services.duplicate_detection import (
    compute_phash,
    hamming_distance,
)

_CASE_ID = "01912345-6789-7abc-8def-0123456789ef"


def test_hamming_distance_identical() -> None:
    """identical hashes have distance 0."""
    assert hamming_distance("abcdef0123456789", "abcdef0123456789") == 0


def test_hamming_distance_known_values() -> None:
    """known bit difference produces correct distance."""
    # 0x0000000000000000 vs 0x0000000000000001 = 1 bit
    assert hamming_distance("0000000000000000", "0000000000000001") == 1


def test_hamming_distance_max() -> None:
    """all bits different gives 64."""
    assert hamming_distance("0000000000000000", "ffffffffffffffff") == 64


def test_hamming_distance_empty_hash() -> None:
    """empty hash returns max distance."""
    assert hamming_distance("", "abcdef0123456789") == 64
    assert hamming_distance("abcdef0123456789", "") == 64


def test_hamming_distance_both_empty() -> None:
    """both empty returns max distance."""
    assert hamming_distance("", "") == 64


def test_compute_phash_missing_pil() -> None:
    """returns empty string when PIL is not available."""
    with patch.dict("sys.modules", {"PIL": None, "PIL.Image": None}):
        # force reimport to trigger ImportError path
        import importlib

        import loom.services.duplicate_detection as mod

        importlib.reload(mod)
        result = mod.compute_phash("/nonexistent/image.jpg")
        assert result == ""
        # reload back to normal
        importlib.reload(mod)


def test_compute_phash_bad_file() -> None:
    """returns empty string for non-existent file."""
    result = compute_phash("/nonexistent/path/image.jpg")
    assert result == ""


def test_compute_phash_valid_image() -> None:
    """produces a 16-char hex string for a valid image."""
    try:
        from PIL import Image
    except ImportError:
        return  # skip if PIL not available

    import tempfile
    from pathlib import Path

    # create a small test image
    img = Image.new("L", (16, 16), color=128)
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
        img.save(f, "PNG")
        tmp_path = f.name

    try:
        result = compute_phash(tmp_path)
        assert len(result) == 16
        # verify it's valid hex
        int(result, 16)
    finally:
        Path(tmp_path).unlink()


def test_compute_phash_deterministic() -> None:
    """same image produces same hash."""
    try:
        from PIL import Image
    except ImportError:
        return  # skip if PIL not available

    import tempfile
    from pathlib import Path

    img = Image.new("L", (16, 16), color=100)
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
        img.save(f, "PNG")
        tmp_path = f.name

    try:
        h1 = compute_phash(tmp_path)
        h2 = compute_phash(tmp_path)
        assert h1 == h2
    finally:
        Path(tmp_path).unlink()


async def test_find_duplicates_groups_correctly() -> None:
    """find_duplicates groups assets with matching sha256."""
    from loom.services.duplicate_detection import (
        find_duplicates,
    )

    # create mock assets with duplicate sha256
    asset1 = MagicMock()
    asset1.id = "00000000-0000-0000-0000-000000000001"
    asset1.sha256_hash = "a" * 64
    asset1.media_type = "image"

    asset2 = MagicMock()
    asset2.id = "00000000-0000-0000-0000-000000000002"
    asset2.sha256_hash = "a" * 64
    asset2.media_type = "image"

    asset3 = MagicMock()
    asset3.id = "00000000-0000-0000-0000-000000000003"
    asset3.sha256_hash = "b" * 64
    asset3.media_type = "document"

    # mock session
    session = AsyncMock()

    # first call returns assets
    mock_assets_result = MagicMock()
    mock_assets_result.scalars.return_value.all.return_value = [
        asset1,
        asset2,
        asset3,
    ]

    # subsequent calls for phash lookups return None
    mock_phash_result = MagicMock()
    mock_phash_result.scalar_one_or_none.return_value = None

    session.execute = AsyncMock(
        side_effect=[
            mock_assets_result,
            mock_phash_result,
            mock_phash_result,
        ]
    )

    clusters = await find_duplicates(session, _CASE_ID)

    assert len(clusters) == 1
    assert clusters[0]["type"] == "exact"
    assert set(clusters[0]["asset_ids"]) == {
        str(asset1.id),
        str(asset2.id),
    }


async def test_find_duplicates_no_assets() -> None:
    """find_duplicates returns empty for single asset."""
    from loom.services.duplicate_detection import (
        find_duplicates,
    )

    asset1 = MagicMock()
    asset1.id = "00000000-0000-0000-0000-000000000001"
    asset1.sha256_hash = "a" * 64
    asset1.media_type = "image"

    session = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = [asset1]
    session.execute = AsyncMock(return_value=mock_result)

    clusters = await find_duplicates(session, _CASE_ID)
    assert clusters == []


async def test_find_duplicates_near_duplicates() -> None:
    """find_duplicates detects phash near-duplicates."""
    from loom.services.duplicate_detection import find_duplicates

    asset1 = MagicMock()
    asset1.id = "00000000-0000-0000-0000-000000000001"
    asset1.sha256_hash = "a" * 64
    asset1.media_type = "image"

    asset2 = MagicMock()
    asset2.id = "00000000-0000-0000-0000-000000000002"
    asset2.sha256_hash = "b" * 64  # different sha
    asset2.media_type = "image"

    session = AsyncMock()
    call_count = 0

    async def mock_execute(query: object) -> MagicMock:
        nonlocal call_count
        call_count += 1
        m = MagicMock()
        if call_count == 1:
            m.scalars.return_value.all.return_value = [asset1, asset2]
        elif call_count == 2:
            # phash for asset1
            m.scalar_one_or_none.return_value = "0000000000000000"
        elif call_count == 3:
            # phash for asset2 (1 bit difference)
            m.scalar_one_or_none.return_value = "0000000000000001"
        return m

    session.execute = AsyncMock(side_effect=mock_execute)

    clusters = await find_duplicates(session, _CASE_ID, threshold=10)
    # should find a near-duplicate cluster
    near = [c for c in clusters if c["type"] == "near"]
    assert len(near) == 1
    assert set(near[0]["asset_ids"]) == {
        str(asset1.id),
        str(asset2.id),
    }


async def test_find_duplicates_no_duplicates() -> None:
    """find_duplicates returns empty when no duplicates."""
    from loom.services.duplicate_detection import find_duplicates

    asset1 = MagicMock()
    asset1.id = "00000000-0000-0000-0000-000000000001"
    asset1.sha256_hash = "a" * 64
    asset1.media_type = "document"

    asset2 = MagicMock()
    asset2.id = "00000000-0000-0000-0000-000000000002"
    asset2.sha256_hash = "b" * 64
    asset2.media_type = "document"

    session = AsyncMock()
    call_count = 0

    async def mock_execute(query: object) -> MagicMock:
        nonlocal call_count
        call_count += 1
        m = MagicMock()
        if call_count == 1:
            m.scalars.return_value.all.return_value = [asset1, asset2]
        else:
            # no phashes (documents)
            m.scalar_one_or_none.return_value = None
        return m

    session.execute = AsyncMock(side_effect=mock_execute)

    clusters = await find_duplicates(session, _CASE_ID)
    assert clusters == []


async def test_create_cluster() -> None:
    """create_cluster persists cluster with members."""
    from loom.services.duplicate_detection import create_cluster

    session = AsyncMock()
    session.add = MagicMock()
    session.flush = AsyncMock()

    # mock begin_nested() as async context manager
    nested_cm = AsyncMock()
    nested_cm.__aenter__ = AsyncMock(return_value=None)
    nested_cm.__aexit__ = AsyncMock(return_value=False)
    session.begin_nested = MagicMock(return_value=nested_cm)

    await create_cluster(
        session,
        _CASE_ID,
        [
            "00000000-0000-0000-0000-000000000001",
            "00000000-0000-0000-0000-000000000002",
        ],
        {
            "00000000-0000-0000-0000-000000000001": "abcdef0123456789",
            "00000000-0000-0000-0000-000000000002": "abcdef0123456780",
        },
    )

    # cluster + 2 members = 3 adds
    assert session.add.call_count == 3
    assert session.flush.await_count == 1


async def test_update_cluster_status() -> None:
    """update_cluster_status changes status."""
    from loom.services.duplicate_detection import (
        update_cluster_status,
    )

    cluster = MagicMock()
    cluster.status = "pending"

    session = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalar_one.return_value = cluster
    session.execute = AsyncMock(return_value=mock_result)

    await update_cluster_status(session, _CASE_ID, "resolved")
    assert cluster.status == "resolved"
    session.flush.assert_awaited_once()


async def test_set_primary_member() -> None:
    """set_primary_member marks one member as primary."""
    from loom.services.duplicate_detection import set_primary_member

    m1 = MagicMock()
    m1.asset_id = "00000000-0000-0000-0000-000000000001"
    m1.is_primary = True

    m2 = MagicMock()
    m2.asset_id = "00000000-0000-0000-0000-000000000002"
    m2.is_primary = False

    session = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = [m1, m2]
    session.execute = AsyncMock(return_value=mock_result)

    await set_primary_member(
        session,
        _CASE_ID,
        "00000000-0000-0000-0000-000000000002",
    )

    assert m1.is_primary is False
    assert m2.is_primary is True
    session.flush.assert_awaited_once()


def test_compute_video_phash_probe_failure() -> None:
    """compute_video_phash returns empty on ffprobe failure."""
    from loom.services.duplicate_detection import compute_video_phash

    with patch(
        "subprocess.run",
        side_effect=Exception("ffprobe not found"),
    ):
        result = compute_video_phash("/nonexistent/video.mp4")
    assert result == ""


def test_compute_video_phash_ffmpeg_failure() -> None:
    """compute_video_phash returns empty on ffmpeg failure."""
    from loom.services.duplicate_detection import compute_video_phash

    # first call (ffprobe) succeeds, second (ffmpeg) fails
    probe_result = MagicMock()
    probe_result.stdout = "10.0\n"

    with patch("subprocess.run") as mock_run:
        mock_run.side_effect = [
            probe_result,
            Exception("ffmpeg failed"),
        ]
        result = compute_video_phash("/nonexistent/video.mp4")
    assert result == ""
