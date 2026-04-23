"""Tests for URL-ingest Temporal activities."""

import hashlib
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID

import pytest

from loom.services.url_ingest.base import ExtractedResource
from loom.workflows import url_ingest_activities

_ASSET_ID = UUID("01912345-6789-7abc-8def-012345678901")
_CASE_ID = UUID("01912345-6789-7abc-8def-012345678902")
_USER_ID = UUID("01912345-6789-7abc-8def-012345678903")


def _make_extracted(
    tmp_path: Path,
    content: bytes = b"test-video-bytes",
) -> ExtractedResource:
    file_path = tmp_path / "abc.mp4"
    file_path.write_bytes(content)
    return ExtractedResource(
        local_path=file_path,
        filename="abc.mp4",
        content_type="video/mp4",
        canonical_url="https://example.com/canonical/abc",
        downloader="yt-dlp",
        downloader_version="2024.08.06",
        source_method="url_yt_dlp",
        response_headers=None,
        extractor_info={"id": "abc", "title": "Test"},
    )


class _AsyncContext:
    def __init__(self, value: Any) -> None:
        self._value = value

    async def __aenter__(self) -> Any:
        return self._value

    async def __aexit__(self, *args: Any) -> None:
        return None


def _make_session(asset: MagicMock) -> MagicMock:
    session = MagicMock()
    find_result = MagicMock()
    find_result.scalar_one_or_none.return_value = asset
    custody_result = MagicMock()
    custody_result.scalar_one_or_none.return_value = None
    calls = {"n": 0}

    async def _execute(_stmt: Any) -> MagicMock:
        calls["n"] += 1
        # first call = select asset, second call = check custody
        return find_result if calls["n"] == 1 else custody_result

    session.execute = _execute
    session.add = MagicMock()
    session.commit = AsyncMock()
    session.flush = AsyncMock()
    return session


def _patch_session(session: MagicMock):
    return patch.object(
        url_ingest_activities,
        "get_db_session",
        return_value=_AsyncContext(session),
    )


def _make_asset() -> MagicMock:
    asset = MagicMock()
    asset.id = _ASSET_ID
    asset.case_id = _CASE_ID
    asset.uploaded_by = _USER_ID
    return asset


@pytest.mark.asyncio
async def test_download_populates_provenance(tmp_path: Path) -> None:
    resource = _make_extracted(tmp_path)
    content = resource.local_path.read_bytes()
    expected_sha = hashlib.sha256(content).hexdigest()

    asset = _make_asset()
    session = _make_session(asset)

    extractor = MagicMock()
    extractor.extract.return_value = resource
    storage = MagicMock()

    with (
        patch.object(
            url_ingest_activities,
            "select_extractor",
            return_value=extractor,
        ),
        patch.object(
            url_ingest_activities,
            "get_minio_client",
            return_value=MagicMock(),
        ),
        patch.object(
            url_ingest_activities,
            "StorageService",
            return_value=storage,
        ),
        _patch_session(session),
    ):
        summary = await (
            url_ingest_activities.download_url_and_record_provenance(
                str(_ASSET_ID),
                "https://example.com/video",
            )
        )

    assert summary["sha256"] == expected_sha
    assert summary["downloader"] == "yt-dlp"
    assert summary["source_method"] == "url_yt_dlp"
    assert asset.source_uri == "https://example.com/video"
    assert asset.source_canonical_uri == ("https://example.com/canonical/abc")
    assert asset.source_downloader == "yt-dlp"
    assert asset.source_downloader_version == "2024.08.06"
    assert asset.source_method == "url_yt_dlp"
    assert asset.source_extractor_info == {
        "id": "abc",
        "title": "Test",
    }
    assert asset.sha256_hash == expected_sha
    assert asset.upload_status == "complete"
    assert asset.source_retrieved_at is not None
    storage.upload_file.assert_called_once()
    # a custody entry was added (first add = asset would have been
    # created elsewhere; here we added the custody entry directly)
    assert session.add.called


@pytest.mark.asyncio
async def test_download_is_idempotent_on_custody(
    tmp_path: Path,
) -> None:
    resource = _make_extracted(tmp_path)
    asset = _make_asset()

    session = MagicMock()
    find_result = MagicMock()
    find_result.scalar_one_or_none.return_value = asset
    # existing custody entry already present
    custody_result = MagicMock()
    custody_result.scalar_one_or_none.return_value = MagicMock()
    calls = {"n": 0}

    async def _execute(_stmt: Any) -> MagicMock:
        calls["n"] += 1
        return find_result if calls["n"] == 1 else custody_result

    session.execute = _execute
    session.add = MagicMock()
    session.commit = AsyncMock()

    extractor = MagicMock()
    extractor.extract.return_value = resource

    with (
        patch.object(
            url_ingest_activities,
            "select_extractor",
            return_value=extractor,
        ),
        patch.object(
            url_ingest_activities,
            "get_minio_client",
            return_value=MagicMock(),
        ),
        patch.object(
            url_ingest_activities,
            "StorageService",
            return_value=MagicMock(),
        ),
        _patch_session(session),
    ):
        await url_ingest_activities.download_url_and_record_provenance(
            str(_ASSET_ID),
            "https://example.com/video",
        )

    # no custody entry is added when one already exists;
    # session.add is never called on the ChainOfCustodyEntry path.
    assert session.add.call_count == 0


@pytest.mark.asyncio
async def test_wayback_snapshot_success(tmp_path: Path) -> None:
    asset = _make_asset()
    session = _make_session(asset)

    archive_url = "https://web.archive.org/web/2026/https://example.com"
    with (
        patch.object(
            url_ingest_activities,
            "snapshot_url",
            return_value=archive_url,
        ),
        _patch_session(session),
    ):
        result = await url_ingest_activities.attempt_wayback_snapshot(
            str(_ASSET_ID),
            "https://example.com",
        )

    assert result == archive_url
    assert asset.source_wayback_url == archive_url
    assert session.add.called


@pytest.mark.asyncio
async def test_wayback_snapshot_none_does_not_touch_asset() -> None:
    asset = _make_asset()
    # give asset a known default wayback state
    asset.source_wayback_url = None
    session = _make_session(asset)

    with (
        patch.object(
            url_ingest_activities,
            "snapshot_url",
            return_value=None,
        ),
        _patch_session(session),
    ):
        result = await url_ingest_activities.attempt_wayback_snapshot(
            str(_ASSET_ID),
            "https://example.com",
        )

    assert result is None
    # snapshot_url returned None, so the activity short-circuits
    # before touching the asset or session.
    assert asset.source_wayback_url is None
    session.add.assert_not_called()
