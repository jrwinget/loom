"""filesystem storage backend for the lite (desktop) deployment.

layout::

    data_dir/
        buckets/
            loom-originals/<key...>
            loom-derivatives/<key...>

WORM semantics are approximated by making files read-only (chmod
0o444) immediately after write. callers that legitimately need to
remove content (soft-delete purge, redaction overwrite) go through
``delete_object`` which first restores write permission.

presigned urls are signed http references of the form
``http://<base>/api/v1/storage/<bucket>/<key>?expires&method&sig``
that the sidecar's own byte-serving endpoint validates and streams.
the base defaults to the loopback bind, so on a desktop install the
url is only reachable from the same machine.
"""

from __future__ import annotations

import hmac
import logging
import shutil
import stat
import time
from collections.abc import Iterator
from hashlib import sha256
from pathlib import Path
from urllib.parse import quote

logger = logging.getLogger(__name__)

# read-only for owner/group/other after write.
_READ_ONLY_MODE = 0o444
_BUCKETS_DIRNAME = "buckets"


class LocalStorageBackend:
    """local-filesystem implementation of :class:`StorageBackend`.

    conforms duck-typed to the protocol; does not inherit to keep
    minio-free environments importable.
    """

    def __init__(
        self,
        data_dir: Path,
        signing_secret: str | None,
        public_base_url: str = "http://127.0.0.1:8000",
    ):
        self._root = (data_dir / _BUCKETS_DIRNAME).resolve()
        # signing secret must be supplied explicitly. a deterministic
        # fallback (e.g. derived from data_dir) would be predictable
        # by any local user and is deliberately rejected — see #57.
        # the Tauri shell persists a random per-install value via
        # tauri-plugin-store and passes it in through settings.
        if not signing_secret:
            raise ValueError(
                "signing_secret is required; pass a random per-install "
                "value (see Settings.storage_signing_secret)."
            )
        self._signing_secret = signing_secret.encode("utf-8")
        # the webview loads media from this origin; trailing slash is
        # stripped so url construction is unambiguous.
        self._public_base_url = public_base_url.rstrip("/")

    # --- path helpers ---------------------------------------------

    def _object_path(self, bucket: str, key: str) -> Path:
        """resolve bucket/key into an absolute path, jailed under root.

        rejects keys that escape the bucket root via traversal (``..``),
        absolute paths, or symlink tricks. raises ``ValueError`` on any
        escape attempt so callers treat a malformed key the same as a
        malformed filename.
        """
        safe_key = key.lstrip("/")
        bucket_root = (self._root / bucket).resolve()
        # resolve(strict=False) normalizes ``..`` without requiring the
        # file to exist; we then assert the result is under bucket_root.
        candidate = (bucket_root / safe_key).resolve()
        try:
            candidate.relative_to(bucket_root)
        except ValueError as exc:
            raise ValueError(
                f"object key escapes bucket root: {bucket}/{key!r}"
            ) from exc
        return candidate

    def _ensure_parent(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)

    def _apply_worm_bit(self, path: Path) -> None:
        """mark a file read-only after write."""
        try:
            path.chmod(_READ_ONLY_MODE)
        except OSError:
            logger.warning(
                "could not apply WORM bit to %s", path, exc_info=True
            )

    def _restore_write(self, path: Path) -> None:
        """restore owner-write for deletion / overwrite."""
        try:
            path.chmod(_READ_ONLY_MODE | stat.S_IWUSR)
        except OSError:
            logger.warning("could not restore write on %s", path, exc_info=True)

    # --- protocol surface -----------------------------------------

    def ensure_buckets(self) -> None:
        from loom.services.storage_backends.base import (
            DERIVATIVES_BUCKET,
            ORIGINALS_BUCKET,
        )

        for bucket in (ORIGINALS_BUCKET, DERIVATIVES_BUCKET):
            (self._root / bucket).mkdir(parents=True, exist_ok=True)

    def upload_file(
        self,
        bucket: str,
        key: str,
        file_path: str,
        content_type: str,
    ) -> None:
        del content_type  # parity with minio api; unused locally
        dest = self._object_path(bucket, key)
        self._ensure_parent(dest)
        if dest.exists():
            # WORM: re-upload to the same key requires deleting the
            # existing read-only file first. callers are expected
            # to verify content equality before overwriting.
            self._restore_write(dest)
            dest.unlink()
        shutil.copyfile(file_path, dest)
        self._apply_worm_bit(dest)

    def upload_bytes(
        self,
        bucket: str,
        key: str,
        data: bytes,
        content_type: str,
    ) -> None:
        del content_type
        dest = self._object_path(bucket, key)
        self._ensure_parent(dest)
        if dest.exists():
            self._restore_write(dest)
            dest.unlink()
        dest.write_bytes(data)
        self._apply_worm_bit(dest)

    def download_file(
        self,
        bucket: str,
        key: str,
        dest_path: str,
    ) -> None:
        src = self._object_path(bucket, key)
        if not src.exists():
            raise FileNotFoundError(f"object not found: {bucket}/{key}")
        shutil.copyfile(src, dest_path)

    def get_presigned_upload_url(
        self,
        bucket: str,
        key: str,
        expires: int = 900,
    ) -> str:
        return self._sign_loopback_url(bucket, key, "PUT", expires)

    def get_presigned_download_url(
        self,
        bucket: str,
        key: str,
        expires: int = 900,
    ) -> str:
        return self._sign_loopback_url(bucket, key, "GET", expires)

    def object_exists(self, bucket: str, key: str) -> bool:
        return self._object_path(bucket, key).is_file()

    def get_object_stream(
        self,
        bucket: str,
        key: str,
        chunk_size: int = 65536,
    ) -> tuple[int, Iterator[bytes]]:
        src = self._object_path(bucket, key)
        if not src.exists():
            raise FileNotFoundError(f"object not found: {bucket}/{key}")
        size = src.stat().st_size
        return size, _stream_file(src, chunk_size)

    def get_object_size(self, bucket: str, key: str) -> int:
        src = self._object_path(bucket, key)
        if not src.exists():
            raise FileNotFoundError(f"object not found: {bucket}/{key}")
        return src.stat().st_size

    def get_object_range(
        self,
        bucket: str,
        key: str,
        start: int,
        end: int,
        chunk_size: int = 65536,
    ) -> Iterator[bytes]:
        src = self._object_path(bucket, key)
        if not src.exists():
            raise FileNotFoundError(f"object not found: {bucket}/{key}")
        return _stream_range(src, start, end, chunk_size)

    def delete_object(self, bucket: str, key: str) -> None:
        dest = self._object_path(bucket, key)
        if not dest.exists():
            return
        self._restore_write(dest)
        dest.unlink()

    # --- signed asset urls ----------------------------------------

    def _sign_loopback_url(
        self,
        bucket: str,
        key: str,
        method: str,
        expires: int,
    ) -> str:
        """build a signed http url the desktop webview can load.

        points at the sidecar's own ``/api/v1/storage`` byte-serving
        endpoint (not a ``loom://`` scheme — the webview cannot load
        that). the signature covers the raw key; the key is
        url-encoded in the path so filenames with spaces work.
        """
        expires_at = int(time.time()) + int(expires)
        sig = self._compute_sig(bucket, key, method, expires_at)
        quoted_key = quote(key, safe="/")
        return (
            f"{self._public_base_url}/api/v1/storage/object/"
            f"{bucket}/{quoted_key}"
            f"?expires={expires_at}&method={method}&sig={sig}"
        )

    def _compute_sig(
        self, bucket: str, key: str, method: str, expires_at: int
    ) -> str:
        payload = f"{method}\n{bucket}\n{key}\n{expires_at}".encode()
        return hmac.new(self._signing_secret, payload, sha256).hexdigest()

    def verify_signature(
        self,
        bucket: str,
        key: str,
        method: str,
        expires_at: int,
        sig: str,
    ) -> bool:
        """constant-time check of a signed asset-stream request.

        the byte-serving endpoint calls this with the already-decoded
        request components, so it is independent of url formatting.
        """
        if time.time() > expires_at:
            return False
        expected = self._compute_sig(bucket, key, method, expires_at)
        return hmac.compare_digest(expected, sig)


def _stream_file(path: Path, chunk_size: int) -> Iterator[bytes]:
    """yield file contents in chunks; closes on exhaustion."""
    with path.open("rb") as fh:
        while True:
            chunk = fh.read(chunk_size)
            if not chunk:
                break
            yield chunk


def _stream_range(
    path: Path, start: int, end: int, chunk_size: int
) -> Iterator[bytes]:
    """yield bytes [start, end] inclusive; closes on exhaustion."""
    remaining = end - start + 1
    with path.open("rb") as fh:
        fh.seek(start)
        while remaining > 0:
            chunk = fh.read(min(chunk_size, remaining))
            if not chunk:
                break
            remaining -= len(chunk)
            yield chunk
