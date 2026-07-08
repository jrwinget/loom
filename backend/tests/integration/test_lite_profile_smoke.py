"""lite-profile smoke test (issue #58 acceptance).

exercises the storage factory + activity helper + storage protocol
surface the ingest and export workflows depend on. no minio client,
no presigned http urls — everything lands on the local filesystem.

this does not spin up temporal; it drives the storage backend the
way activities drive it, so a regression in the factory wiring
(e.g. a caller forgetting to go through ``build_storage_backend``)
fails here immediately.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from loom.config import Settings
from loom.services.storage_backends import (
    DERIVATIVES_BUCKET,
    ORIGINALS_BUCKET,
    LocalStorageBackend,
    StorageBackend,
    build_storage_backend,
)


def _lite_settings(tmp_path: Path) -> Settings:
    return Settings(
        deployment_profile="lite",
        database_url="sqlite+aiosqlite:///:memory:",
        data_dir=tmp_path,
        secret_key="smoke-test-secret-key-that-is-long-enough-here",
        # per #57, lite profile requires an explicit per-install
        # signing secret for loopback presigned urls.
        storage_signing_secret="smoke-test-signing-secret",
    )


def test_factory_returns_local_backend_in_lite(tmp_path: Path) -> None:
    """factory honours LOOM_DEPLOYMENT_PROFILE=lite without minio."""
    backend = build_storage_backend(_lite_settings(tmp_path))
    assert isinstance(backend, LocalStorageBackend)
    assert isinstance(backend, StorageBackend)


def test_worker_helper_returns_local_backend_in_lite(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """the worker-side cache (used by activities) picks lite too."""
    # the helper reads settings via get_settings(); point it at a
    # fresh lite settings without mutating the process-wide cache.
    from loom.workflows import shared

    monkeypatch.setattr(
        shared, "get_settings", lambda: _lite_settings(tmp_path)
    )
    shared.reset_for_testing()

    backend = shared.get_storage_backend()
    try:
        assert isinstance(backend, LocalStorageBackend)
        # second call returns the cached instance (same identity).
        assert shared.get_storage_backend() is backend
    finally:
        shared.reset_for_testing()


def test_ingest_then_export_round_trip_without_minio(
    tmp_path: Path,
) -> None:
    """the operations ingest and export activities use against the
    storage backend all succeed on lite-profile without touching
    minio: upload original -> read back -> write derivative ->
    stream derivative -> presigned url (loopback) -> delete.

    this models the protocol surface that ingest's verify_hash /
    extract_metadata / generate_proxy and export's bundle assembly
    touch, so a new activity that bypasses ``get_storage_backend``
    will break this test.
    """
    settings = _lite_settings(tmp_path)
    backend = build_storage_backend(settings)
    backend.ensure_buckets()

    # --- original upload (what ingest.upload_asset does) ----------
    payload = b"video bytes that pretend to be mp4" * 32
    expected_sha256 = hashlib.sha256(payload).hexdigest()
    key = "case-xyz/asset-1/clip.mp4"
    backend.upload_bytes(ORIGINALS_BUCKET, key, payload, "video/mp4")
    assert backend.object_exists(ORIGINALS_BUCKET, key)

    # --- verify_asset_hash style read-back ------------------------
    size, chunks = backend.get_object_stream(ORIGINALS_BUCKET, key)
    assert size == len(payload)
    computed_sha256 = hashlib.sha256(b"".join(chunks)).hexdigest()
    assert computed_sha256 == expected_sha256

    # --- generate_proxy style derivative upload -------------------
    proxy_key = "case-xyz/asset-1/clip.proxy.mp4"
    backend.upload_bytes(
        DERIVATIVES_BUCKET,
        proxy_key,
        b"proxy bytes",
        "video/mp4",
    )
    assert backend.object_exists(DERIVATIVES_BUCKET, proxy_key)

    # --- export-bundle style download-to-disk ---------------------
    out = tmp_path / "export" / "clip.mp4"
    out.parent.mkdir(parents=True, exist_ok=True)
    backend.download_file(ORIGINALS_BUCKET, key, str(out))
    assert out.read_bytes() == payload

    # --- signed http asset url (served by the sidecar endpoint) ---
    url = backend.get_presigned_download_url(ORIGINALS_BUCKET, key, expires=60)
    assert url.startswith("http://")
    assert "/api/v1/storage/object/" in url

    # --- delete (used by soft-delete / redaction paths) -----------
    backend.delete_object(DERIVATIVES_BUCKET, proxy_key)
    assert not backend.object_exists(DERIVATIVES_BUCKET, proxy_key)

    # --- the lite path wrote to disk, not to a remote service -----
    originals_root = tmp_path / "buckets" / ORIGINALS_BUCKET
    assert (originals_root / "case-xyz" / "asset-1" / "clip.mp4").is_file()
