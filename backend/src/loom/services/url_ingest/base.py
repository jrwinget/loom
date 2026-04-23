"""Base types and protocols for URL extractors."""

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol


@dataclass(frozen=True)
class ExtractedResource:
    """Result of a URL extraction: local bytes plus provenance."""

    local_path: Path
    filename: str
    content_type: str
    canonical_url: str
    downloader: str
    downloader_version: str
    source_method: str
    response_headers: dict[str, str] | None = None
    extractor_info: dict[str, Any] | None = None


class Extractor(Protocol):
    """Protocol implemented by every URL extractor."""

    downloader: str
    source_method: str

    def can_handle(self, url: str) -> bool: ...

    def extract(
        self,
        url: str,
        dest_dir: Path,
    ) -> ExtractedResource: ...


class ExtractorUnavailableError(RuntimeError):
    """The matched extractor's optional dep is not installed."""


class ExtractionError(RuntimeError):
    """Network, private content, or other extractor failure."""
