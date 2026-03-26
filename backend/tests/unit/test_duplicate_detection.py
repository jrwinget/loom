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
