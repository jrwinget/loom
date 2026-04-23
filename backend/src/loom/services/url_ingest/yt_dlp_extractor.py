"""yt-dlp extractor with graceful degradation."""

import logging
from pathlib import Path
from typing import Any

from loom.services.url_ingest.base import (
    ExtractedResource,
    ExtractionError,
    ExtractorUnavailableError,
)

logger = logging.getLogger(__name__)

try:
    import yt_dlp

    _AVAILABLE = True
    _VERSION = getattr(yt_dlp, "version", None)
    _VERSION_STR = getattr(_VERSION, "__version__", "unknown")
except ImportError:
    _AVAILABLE = False
    _VERSION_STR = "unknown"


def is_available() -> bool:
    """Return True when yt-dlp is importable."""
    return _AVAILABLE


class YtDlpExtractor:
    """Downloads a resource via yt-dlp.

    Handles any URL yt-dlp recognizes (YouTube, Twitter, TikTok,
    Vimeo, Facebook public, etc). Never attempts to bypass
    authentication — if the site requires credentials, the
    extractor's own error is surfaced as an ExtractionError.
    """

    downloader = "yt-dlp"
    source_method = "url_yt_dlp"

    def can_handle(self, url: str) -> bool:
        if not _AVAILABLE:
            return False
        try:
            from yt_dlp.extractor import gen_extractors

            for extractor in gen_extractors():
                if extractor.suitable(url) and extractor.IE_NAME != "generic":
                    return True
        except Exception:
            # unexpected failure while probing - defer to fallback
            logger.debug(
                "yt-dlp site-list probe failed for %s",
                url,
                exc_info=True,
            )
            return False
        return False

    def extract(
        self,
        url: str,
        dest_dir: Path,
    ) -> ExtractedResource:
        if not _AVAILABLE:
            raise ExtractorUnavailableError(
                "yt-dlp is not installed; install the 'url-ingest' extra"
            )

        opts = {
            "outtmpl": str(dest_dir / "%(id)s.%(ext)s"),
            "quiet": True,
            "noplaylist": True,
            "no_warnings": True,
        }
        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(url, download=True)
                local_path = Path(ydl.prepare_filename(info))
        except Exception as exc:
            msg = f"yt-dlp extraction failed for {url}: {exc}"
            raise ExtractionError(msg) from exc

        if not local_path.exists():
            msg = (
                f"yt-dlp reported success but produced no file at {local_path}"
            )
            raise ExtractionError(msg)

        canonical = info.get("webpage_url") or info.get("original_url") or url
        content_type = _guess_content_type(local_path, info)
        extractor_info: dict[str, Any] = {
            "id": info.get("id"),
            "title": info.get("title"),
            "uploader": info.get("uploader"),
            "duration": info.get("duration"),
            "extractor": info.get("extractor"),
        }

        return ExtractedResource(
            local_path=local_path,
            filename=local_path.name,
            content_type=content_type,
            canonical_url=canonical,
            downloader=self.downloader,
            downloader_version=_VERSION_STR,
            source_method=self.source_method,
            response_headers=None,
            extractor_info=extractor_info,
        )


def _guess_content_type(
    local_path: Path,
    info: dict[str, Any],
) -> str:
    """Derive a MIME type from yt-dlp info or file suffix."""
    if info.get("ext") == "mp4":
        return "video/mp4"
    if info.get("ext") == "webm":
        return "video/webm"
    if info.get("ext") == "mp3":
        return "audio/mpeg"
    if info.get("ext") == "m4a":
        return "audio/mp4"
    # fall back to generic video — magic-byte validation in the
    # activity layer will confirm or reject downstream.
    suffix = local_path.suffix.lower().lstrip(".")
    if suffix in {"mp4", "mov", "mkv"}:
        return f"video/{suffix}"
    return "application/octet-stream"
