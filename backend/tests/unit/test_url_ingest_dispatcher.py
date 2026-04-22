"""Tests for URL -> extractor selection."""

import socket
from collections.abc import Iterator
from unittest.mock import patch

import pytest

from loom.services.url_ingest import (
    ExtractionError,
    select_extractor,
)
from loom.services.url_ingest.archive_extractor import (
    ArchiveExtractor,
)
from loom.services.url_ingest.http_extractor import HttpExtractor
from loom.services.url_ingest.yt_dlp_extractor import YtDlpExtractor


@pytest.fixture(autouse=True)
def _stub_dns() -> Iterator[None]:
    """pretend every hostname resolves to a public IP.

    the dispatcher's SSRF guard calls socket.getaddrinfo; in a
    hermetic test environment we stub it out so selection logic
    is exercised without touching the network.
    """
    fake = [
        (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 443)),
    ]
    with patch(
        "loom.services.webhook.socket.getaddrinfo",
        return_value=fake,
    ):
        yield


def test_archive_details_url_selects_archive() -> None:
    extractor = select_extractor("https://archive.org/details/xyz-2020-protest")
    assert isinstance(extractor, ArchiveExtractor)


def test_archive_download_url_selects_archive() -> None:
    extractor = select_extractor(
        "https://archive.org/download/xyz-2020/video.mp4"
    )
    assert isinstance(extractor, ArchiveExtractor)


@pytest.mark.parametrize(
    "url",
    [
        "https://www.youtube.com/watch?v=abc123",
        "https://twitter.com/user/status/1234567890",
        "https://www.tiktok.com/@user/video/987654321",
    ],
)
def test_social_and_video_urls_select_yt_dlp(url: str) -> None:
    # if yt-dlp isn't installed, the fallback picks up -- this
    # test only checks the selection priority when yt-dlp is
    # available.
    from loom.services.url_ingest import yt_dlp_extractor

    if not yt_dlp_extractor.is_available():
        pytest.skip("yt-dlp not installed")
    extractor = select_extractor(url)
    assert isinstance(extractor, YtDlpExtractor)


@pytest.mark.parametrize(
    "url",
    [
        "https://example.com/video.mp4",
        "https://newsite.com/raw.mp4",
        "https://static.example.org/documents/report.pdf",
    ],
)
def test_direct_file_urls_fall_back_to_http(url: str) -> None:
    extractor = select_extractor(url)
    assert isinstance(extractor, HttpExtractor)


def test_non_http_url_raises() -> None:
    with pytest.raises(ExtractionError):
        select_extractor("ftp://example.com/file.mp4")
