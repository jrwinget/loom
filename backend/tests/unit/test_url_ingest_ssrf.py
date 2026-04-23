"""SSRF protection tests for the URL ingest dispatcher."""

import socket
from unittest.mock import patch

import pytest

from loom.services.url_ingest.base import ExtractionError
from loom.services.url_ingest.dispatcher import select_extractor


def _fake_getaddrinfo(
    ip: str,
) -> list[tuple[int, int, int, str, tuple[str, int]]]:
    """build a fake socket.getaddrinfo return value."""
    return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (ip, 443))]


@pytest.mark.parametrize(
    "blocked_ip",
    [
        "127.0.0.1",
        "10.1.2.3",
        "172.16.5.5",
        "192.168.0.1",
        "169.254.169.254",  # aws metadata
    ],
)
def test_rejects_private_ipv4(blocked_ip: str) -> None:
    """dispatcher rejects urls whose hostname resolves to private IP."""
    with patch(
        "loom.services.webhook.socket.getaddrinfo",
        return_value=_fake_getaddrinfo(blocked_ip),
    ):
        with pytest.raises(ExtractionError) as exc:
            select_extractor("https://attacker.example.com/path")
        assert "private" in str(exc.value) or "reserved" in str(exc.value)


@pytest.mark.parametrize(
    "blocked_ip",
    ["::1", "fc00::1", "fe80::1"],
)
def test_rejects_private_ipv6(blocked_ip: str) -> None:
    """dispatcher rejects urls resolving to loopback/ULA/link-local v6."""
    fake = [(socket.AF_INET6, socket.SOCK_STREAM, 6, "", (blocked_ip, 443))]
    with (
        patch(
            "loom.services.webhook.socket.getaddrinfo",
            return_value=fake,
        ),
        pytest.raises(ExtractionError),
    ):
        select_extractor("https://attacker.example.com/path")


@pytest.mark.parametrize(
    "url",
    [
        "file:///etc/passwd",
        "data:text/plain;base64,SGVsbG8=",
        "ftp://example.com/file.mp4",
        "gopher://example.com/",
    ],
)
def test_rejects_non_http_schemes(url: str) -> None:
    """non-http(s) schemes are rejected before DNS lookup."""
    with pytest.raises(ExtractionError) as exc:
        select_extractor(url)
    msg = str(exc.value).lower()
    assert "scheme" in msg or "no extractor" in msg


def test_rejects_localhost_rebinding() -> None:
    """hostname that A-records to 127.0.0.1 is still blocked."""
    with (
        patch(
            "loom.services.webhook.socket.getaddrinfo",
            return_value=_fake_getaddrinfo("127.0.0.1"),
        ),
        pytest.raises(ExtractionError),
    ):
        select_extractor("https://localhost.evil.example/")


def test_allows_public_ip() -> None:
    """public ipv4 that doesn't match any blocked range passes through."""
    with patch(
        "loom.services.webhook.socket.getaddrinfo",
        return_value=_fake_getaddrinfo("93.184.216.34"),  # example.com
    ):
        extractor = select_extractor("https://example.com/video.mp4")
        assert extractor is not None
