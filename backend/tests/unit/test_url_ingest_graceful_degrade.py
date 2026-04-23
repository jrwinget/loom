"""Tests for graceful degradation when optional deps are missing."""

from pathlib import Path

import pytest

from loom.services.url_ingest import (
    ExtractorUnavailableError,
)
from loom.services.url_ingest.archive_extractor import (
    ArchiveExtractor,
)
from loom.services.url_ingest.http_extractor import HttpExtractor
from loom.services.url_ingest.yt_dlp_extractor import YtDlpExtractor


def test_yt_dlp_unavailable_raises(monkeypatch, tmp_path: Path) -> None:
    import loom.services.url_ingest.yt_dlp_extractor as mod

    monkeypatch.setattr(mod, "_AVAILABLE", False)
    extractor = YtDlpExtractor()
    # can_handle returns False when unavailable (so selection
    # falls through to the next extractor).
    assert extractor.can_handle("https://www.youtube.com/watch?v=abc") is False
    # direct extract() still raises for callers that bypass
    # can_handle.
    with pytest.raises(ExtractorUnavailableError):
        extractor.extract("https://youtu.be/abc", tmp_path)


def test_archive_unavailable_raises(monkeypatch, tmp_path: Path) -> None:
    import loom.services.url_ingest.archive_extractor as mod

    monkeypatch.setattr(mod, "_AVAILABLE", False)
    extractor = ArchiveExtractor()
    # can_handle is URL-only and still True for archive.org URLs
    assert extractor.can_handle("https://archive.org/details/foo") is True
    with pytest.raises(ExtractorUnavailableError):
        extractor.extract(
            "https://archive.org/details/foo",
            tmp_path,
        )


def test_http_extractor_always_available() -> None:
    extractor = HttpExtractor()
    assert extractor.can_handle("https://example.com/file.mp4")
    assert extractor.can_handle("http://example.com/file.mp4")
    assert not extractor.can_handle("ftp://example.com/file.mp4")
