"""Provenance integrity test for URL ingestion (issue #46).

Explicitly asserts every provenance field required by the issue's
acceptance criteria is captured after a full simulated ingest:
- source URL
- canonical URL
- retrieval UTC timestamp
- downloader name + version
- response headers (HTTP fallback path)
- SHA-256 of downloaded bytes
- Wayback snapshot URL
- chain-of-custody entries with the correct fields
"""

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


class _AsyncContext:
    def __init__(self, value: Any) -> None:
        self._value = value

    async def __aenter__(self) -> Any:
        return self._value

    async def __aexit__(self, *args: Any) -> None:
        return None


def _make_asset() -> MagicMock:
    asset = MagicMock()
    asset.id = _ASSET_ID
    asset.case_id = _CASE_ID
    asset.uploaded_by = _USER_ID
    asset.source_wayback_url = None
    return asset


def _make_session(asset: MagicMock) -> tuple[MagicMock, list[Any]]:
    """Return a session mock + a list that captures added rows."""
    session = MagicMock()
    find_result = MagicMock()
    find_result.scalar_one_or_none.return_value = asset
    custody_result = MagicMock()
    custody_result.scalar_one_or_none.return_value = None
    calls = {"n": 0}

    async def _execute(_stmt: Any) -> MagicMock:
        calls["n"] += 1
        return find_result if calls["n"] == 1 else custody_result

    added: list[Any] = []

    def _add(obj: Any) -> None:
        added.append(obj)

    session.execute = _execute
    session.add = _add
    session.commit = AsyncMock()
    session.flush = AsyncMock()
    return session, added


@pytest.mark.asyncio
async def test_full_http_provenance_captured(
    tmp_path: Path,
) -> None:
    content = b"downloaded-http-bytes"
    file_path = tmp_path / "video.mp4"
    file_path.write_bytes(content)
    expected_sha = hashlib.sha256(content).hexdigest()

    resource = ExtractedResource(
        local_path=file_path,
        filename="video.mp4",
        content_type="video/mp4",
        canonical_url="https://example.com/final/video.mp4",
        downloader="http",
        downloader_version="0.27.0",
        source_method="url_http",
        response_headers={
            "content-type": "video/mp4",
            "content-length": str(len(content)),
            "etag": "abc123",
        },
        extractor_info=None,
    )

    asset = _make_asset()
    session, added = _make_session(asset)
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
        patch.object(
            url_ingest_activities,
            "get_db_session",
            return_value=_AsyncContext(session),
        ),
    ):
        await url_ingest_activities.download_url_and_record_provenance(
            str(_ASSET_ID),
            "https://example.com/video.mp4",
        )

    # assert each provenance field landed on the asset
    assert asset.source_uri == "https://example.com/video.mp4"
    assert asset.source_canonical_uri == ("https://example.com/final/video.mp4")
    assert asset.source_method == "url_http"
    assert asset.source_downloader == "http"
    assert asset.source_downloader_version == "0.27.0"
    assert asset.source_retrieved_at is not None
    assert asset.source_response_headers == {
        "content-type": "video/mp4",
        "content-length": str(len(content)),
        "etag": "abc123",
    }
    assert asset.sha256_hash == expected_sha
    assert asset.file_size_bytes == len(content)

    # exactly one custody entry was added with the required fields
    assert len(added) == 1
    custody = added[0]
    detail = custody.detail
    assert detail["url"] == "https://example.com/video.mp4"
    assert detail["canonical_url"] == ("https://example.com/final/video.mp4")
    assert detail["downloader"] == "http"
    assert detail["downloader_version"] == "0.27.0"
    assert detail["sha256"] == expected_sha
    assert detail["source_method"] == "url_http"
    assert "retrieved_at" in detail
    # retrieved_at is an ISO-8601 string with timezone info
    assert detail["retrieved_at"].endswith("+00:00") or (
        detail["retrieved_at"].endswith("Z")
    )


@pytest.mark.asyncio
async def test_wayback_snapshot_recorded_separately(
    tmp_path: Path,
) -> None:
    asset = _make_asset()
    session, added = _make_session(asset)
    archive_url = "https://web.archive.org/web/2026/https://example.com"

    with (
        patch.object(
            url_ingest_activities,
            "snapshot_url",
            return_value=archive_url,
        ),
        patch.object(
            url_ingest_activities,
            "get_db_session",
            return_value=_AsyncContext(session),
        ),
    ):
        await url_ingest_activities.attempt_wayback_snapshot(
            str(_ASSET_ID),
            "https://example.com",
        )

    assert asset.source_wayback_url == archive_url
    assert len(added) == 1
    custody = added[0]
    assert custody.action == "wayback_snapshot"
    assert custody.detail == {
        "url": "https://example.com",
        "archive_url": archive_url,
    }
