import hashlib
import tempfile
from pathlib import Path

from loom.services.hashing import (
    compute_hashes_from_bytes,
    compute_hashes_from_file,
    compute_hashes_from_stream,
)

_TEST_DATA = b"hello, loom evidence platform!"


def test_compute_hashes_from_bytes_known_values() -> None:
    """sha-256 and sha-512 match hashlib directly."""
    expected_256 = hashlib.sha256(_TEST_DATA).hexdigest()
    expected_512 = hashlib.sha512(_TEST_DATA).hexdigest()

    sha256, sha512 = compute_hashes_from_bytes(_TEST_DATA)

    assert sha256 == expected_256
    assert sha512 == expected_512


def test_compute_hashes_from_bytes_empty() -> None:
    """hashes of empty bytes are correct."""
    expected_256 = hashlib.sha256(b"").hexdigest()
    expected_512 = hashlib.sha512(b"").hexdigest()

    sha256, sha512 = compute_hashes_from_bytes(b"")

    assert sha256 == expected_256
    assert sha512 == expected_512


def test_compute_hashes_from_file() -> None:
    """file hashing matches bytes hashing."""
    expected = compute_hashes_from_bytes(_TEST_DATA)

    with tempfile.NamedTemporaryFile(delete=False) as f:
        f.write(_TEST_DATA)
        tmp_path = Path(f.name)

    try:
        result = compute_hashes_from_file(tmp_path)
        assert result == expected
    finally:
        tmp_path.unlink()


async def test_compute_hashes_from_stream() -> None:
    """streaming hash produces same result as bytes hash."""
    expected = compute_hashes_from_bytes(_TEST_DATA)

    async def _stream():
        # split into small chunks
        for i in range(0, len(_TEST_DATA), 8):
            yield _TEST_DATA[i : i + 8]

    result = await compute_hashes_from_stream(_stream())
    assert result == expected
