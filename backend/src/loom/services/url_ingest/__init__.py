"""URL ingestion services.

Public re-exports for the URL extraction pipeline. Each extractor
degrades gracefully when its optional dependency is not installed.
"""

from loom.services.url_ingest.archive_extractor import ArchiveExtractor
from loom.services.url_ingest.base import (
    ExtractedResource,
    ExtractionError,
    Extractor,
    ExtractorUnavailableError,
)
from loom.services.url_ingest.dispatcher import select_extractor
from loom.services.url_ingest.http_extractor import HttpExtractor
from loom.services.url_ingest.wayback import snapshot_url
from loom.services.url_ingest.yt_dlp_extractor import YtDlpExtractor

__all__ = [
    "ArchiveExtractor",
    "ExtractedResource",
    "ExtractionError",
    "Extractor",
    "ExtractorUnavailableError",
    "HttpExtractor",
    "YtDlpExtractor",
    "select_extractor",
    "snapshot_url",
]
