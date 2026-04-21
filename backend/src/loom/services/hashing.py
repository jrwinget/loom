import hashlib
from collections.abc import AsyncIterator, Iterator
from pathlib import Path

_CHUNK_SIZE = 65536  # 64kb


def compute_hashes_from_bytes(data: bytes) -> tuple[str, str]:
    """compute sha-256 and sha-512 of bytes, return hex digests."""
    sha256 = hashlib.sha256(data).hexdigest()
    sha512 = hashlib.sha512(data).hexdigest()
    return sha256, sha512


def compute_hashes_from_file(
    file_path: Path,
) -> tuple[str, str]:
    """stream file in 64kb chunks, compute both hashes."""
    sha256 = hashlib.sha256()
    sha512 = hashlib.sha512()

    with open(file_path, "rb") as f:
        while True:
            chunk = f.read(_CHUNK_SIZE)
            if not chunk:
                break
            sha256.update(chunk)
            sha512.update(chunk)

    return sha256.hexdigest(), sha512.hexdigest()


def compute_hashes_from_iterator(
    chunks: Iterator[bytes],
) -> tuple[str, str]:
    """compute hashes from a synchronous chunk iterator."""
    sha256 = hashlib.sha256()
    sha512 = hashlib.sha512()

    for chunk in chunks:
        sha256.update(chunk)
        sha512.update(chunk)

    return sha256.hexdigest(), sha512.hexdigest()


async def compute_hashes_from_stream(
    stream: AsyncIterator[bytes],
) -> tuple[str, str]:
    """async version for streaming uploads."""
    sha256 = hashlib.sha256()
    sha512 = hashlib.sha512()

    async for chunk in stream:
        sha256.update(chunk)
        sha512.update(chunk)

    return sha256.hexdigest(), sha512.hexdigest()
