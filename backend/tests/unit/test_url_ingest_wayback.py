"""Tests for the Wayback Machine snapshot helper."""

from unittest.mock import MagicMock

from loom.services.url_ingest import wayback


def test_returns_none_when_savepagenow_missing(monkeypatch) -> None:
    monkeypatch.setattr(wayback, "_AVAILABLE", False)
    assert wayback.snapshot_url("https://example.com") is None


def test_returns_archive_url_on_success(monkeypatch) -> None:
    monkeypatch.setattr(wayback, "_AVAILABLE", True)
    mock_spn = MagicMock()
    mock_spn.capture.return_value = (
        "https://web.archive.org/web/2026/https://example.com"
    )
    monkeypatch.setattr(wayback, "savepagenow", mock_spn, raising=False)
    result = wayback.snapshot_url("https://example.com")
    assert result == ("https://web.archive.org/web/2026/https://example.com")


def test_returns_none_when_capture_raises(monkeypatch) -> None:
    monkeypatch.setattr(wayback, "_AVAILABLE", True)
    mock_spn = MagicMock()
    mock_spn.capture.side_effect = RuntimeError("429 throttled")
    monkeypatch.setattr(wayback, "savepagenow", mock_spn, raising=False)
    result = wayback.snapshot_url("https://example.com")
    assert result is None


def test_returns_none_when_capture_returns_empty(monkeypatch) -> None:
    monkeypatch.setattr(wayback, "_AVAILABLE", True)
    mock_spn = MagicMock()
    mock_spn.capture.return_value = ""
    monkeypatch.setattr(wayback, "savepagenow", mock_spn, raising=False)
    assert wayback.snapshot_url("https://example.com") is None
