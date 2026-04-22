"""archive.org (internetarchive) extractor."""

import logging
import re
from pathlib import Path
from typing import Any

from loom.services.url_ingest.base import (
    ExtractedResource,
    ExtractionError,
    ExtractorUnavailableError,
)

logger = logging.getLogger(__name__)

try:
    import internetarchive

    _AVAILABLE = True
    _VERSION_STR = getattr(internetarchive, "__version__", "unknown")
except ImportError:
    _AVAILABLE = False
    _VERSION_STR = "unknown"

_DETAILS_RE = re.compile(
    r"^https?://archive\.org/details/([^/?#]+)",
    re.IGNORECASE,
)
_DOWNLOAD_RE = re.compile(
    r"^https?://archive\.org/download/([^/]+)(?:/([^?#]+))?",
    re.IGNORECASE,
)


def is_available() -> bool:
    """Return True when internetarchive is importable."""
    return _AVAILABLE


def _parse_identifier(url: str) -> tuple[str, str | None]:
    """Extract (identifier, maybe filename) from an archive URL."""
    m = _DETAILS_RE.match(url)
    if m:
        return m.group(1), None
    m = _DOWNLOAD_RE.match(url)
    if m:
        return m.group(1), m.group(2)
    msg = f"not an archive.org URL: {url}"
    raise ExtractionError(msg)


class ArchiveExtractor:
    """Downloads a resource from archive.org."""

    downloader = "internetarchive"
    source_method = "url_archive_org"

    def can_handle(self, url: str) -> bool:
        return bool(_DETAILS_RE.match(url) or _DOWNLOAD_RE.match(url))

    def extract(
        self,
        url: str,
        dest_dir: Path,
    ) -> ExtractedResource:
        if not _AVAILABLE:
            raise ExtractorUnavailableError(
                "internetarchive is not installed; "
                "install the 'url-ingest' extra"
            )

        identifier, requested_filename = _parse_identifier(url)

        try:
            item = internetarchive.get_item(identifier)
            download_kwargs: dict[str, Any] = {
                "destdir": str(dest_dir),
                "ignore_existing": True,
            }
            if requested_filename:
                # use glob_pattern rather than `files=` — the latter
                # expects File objects per internetarchive's type hints.
                download_kwargs["glob_pattern"] = requested_filename
            internetarchive.download(identifier, **download_kwargs)
        except Exception as exc:
            msg = f"archive.org extraction failed for {url}: {exc}"
            raise ExtractionError(msg) from exc

        local_path = _resolve_downloaded_file(
            dest_dir,
            identifier,
            requested_filename,
        )
        content_type = _guess_content_type(local_path)
        metadata: dict[str, Any] = dict(getattr(item, "metadata", {}) or {})
        extractor_info: dict[str, Any] = {
            "identifier": identifier,
            "title": metadata.get("title"),
            "uploader": metadata.get("uploader"),
            "collection": metadata.get("collection"),
        }

        return ExtractedResource(
            local_path=local_path,
            filename=local_path.name,
            content_type=content_type,
            canonical_url=f"https://archive.org/details/{identifier}",
            downloader=self.downloader,
            downloader_version=_VERSION_STR,
            source_method=self.source_method,
            response_headers=None,
            extractor_info=extractor_info,
        )


def _resolve_downloaded_file(
    dest_dir: Path,
    identifier: str,
    requested_filename: str | None,
) -> Path:
    """Find the downloaded file under dest_dir/<identifier>/."""
    item_dir = dest_dir / identifier
    if requested_filename:
        candidate = item_dir / requested_filename
        if candidate.exists():
            return candidate

    if not item_dir.exists():
        msg = (
            f"expected archive.org download directory {item_dir} does not exist"
        )
        raise ExtractionError(msg)

    files = sorted(item_dir.iterdir())
    if not files:
        msg = f"archive.org download produced no files in {item_dir}"
        raise ExtractionError(msg)
    return files[0]


def _guess_content_type(local_path: Path) -> str:
    """Derive a MIME type from the file suffix."""
    suffix = local_path.suffix.lower().lstrip(".")
    mapping = {
        "mp4": "video/mp4",
        "mov": "video/quicktime",
        "mkv": "video/x-matroska",
        "webm": "video/webm",
        "mp3": "audio/mpeg",
        "wav": "audio/wav",
        "flac": "audio/flac",
        "ogg": "audio/ogg",
        "jpg": "image/jpeg",
        "jpeg": "image/jpeg",
        "png": "image/png",
        "pdf": "application/pdf",
    }
    return mapping.get(suffix, "application/octet-stream")
