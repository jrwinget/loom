"""URL -> extractor selection."""

from loom.services.url_ingest.archive_extractor import (
    ArchiveExtractor,
)
from loom.services.url_ingest.base import (
    ExtractionError,
    Extractor,
)
from loom.services.url_ingest.http_extractor import HttpExtractor
from loom.services.url_ingest.yt_dlp_extractor import YtDlpExtractor
from loom.services.webhook import assert_public_url


def select_extractor(url: str) -> Extractor:
    """Return the highest-priority extractor that claims the URL.

    Priority order:
      1. archive.org (always claims archive.org URLs)
      2. yt-dlp (whitelists via yt-dlp's own site list)
      3. HTTP fallback (always claims http/https URLs)

    Enforces SSRF protection before dispatch: rejects non-http(s)
    schemes and any hostname that resolves to a loopback, private,
    link-local, or reserved address. This guard is centralized so
    all three extractors receive the same treatment.

    Raises ExtractionError if the URL is blocked or if no
    extractor can handle it.
    """
    try:
        assert_public_url(url)
    except ValueError as err:
        raise ExtractionError(str(err)) from err

    candidates: list[Extractor] = [
        ArchiveExtractor(),
        YtDlpExtractor(),
        HttpExtractor(),
    ]
    for extractor in candidates:
        if extractor.can_handle(url):
            return extractor
    msg = f"no extractor can handle URL: {url}"
    raise ExtractionError(msg)
