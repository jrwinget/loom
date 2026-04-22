"""Generic HTTP fallback extractor.

This extractor has no optional dependency — httpx is a core dep —
so it always reports available. It streams the response to disk,
captures response headers verbatim, and derives a filename from
Content-Disposition or the URL path.
"""

import email.utils
import logging
import re
from pathlib import Path
from urllib.parse import unquote, urlparse

import httpx

from loom.services.url_ingest.base import (
    ExtractedResource,
    ExtractionError,
)

logger = logging.getLogger(__name__)

_VERSION_STR = httpx.__version__

_STREAM_CHUNK_BYTES = 64 * 1024


class HttpExtractor:
    """Fallback: stream a URL to disk with httpx."""

    downloader = "http"
    source_method = "url_http"

    def can_handle(self, url: str) -> bool:
        parsed = urlparse(url)
        return parsed.scheme in ("http", "https")

    def extract(
        self,
        url: str,
        dest_dir: Path,
    ) -> ExtractedResource:
        try:
            with (
                httpx.Client(
                    follow_redirects=True,
                    timeout=60,
                ) as client,
                client.stream("GET", url) as response,
            ):
                response.raise_for_status()
                filename = _derive_filename(url, response.headers)
                content_type = (
                    response.headers.get("content-type")
                    or "application/octet-stream"
                )
                local_path = dest_dir / filename
                with local_path.open("wb") as fh:
                    for chunk in response.iter_bytes(
                        _STREAM_CHUNK_BYTES,
                    ):
                        fh.write(chunk)
                response_headers = dict(response.headers.items())
                canonical = str(response.url)
        except httpx.HTTPError as exc:
            msg = f"http extraction failed for {url}: {exc}"
            raise ExtractionError(msg) from exc

        # normalize content-type by stripping charset etc.
        primary_type = content_type.split(";", 1)[0].strip()

        return ExtractedResource(
            local_path=local_path,
            filename=filename,
            content_type=primary_type,
            canonical_url=canonical,
            downloader=self.downloader,
            downloader_version=_VERSION_STR,
            source_method=self.source_method,
            response_headers=response_headers,
            extractor_info=None,
        )


_DISP_RE = re.compile(r'filename\*?="?([^";]+)"?', re.IGNORECASE)
_UNSAFE = re.compile(r"[\\/\x00-\x1f]")


def _derive_filename(
    url: str,
    headers: httpx.Headers,
) -> str:
    """Pull a filename from Content-Disposition or the URL path.

    Falls back to 'download' when neither source yields a usable
    basename. Any path separators or control chars are stripped.
    """
    disp = headers.get("content-disposition")
    if disp:
        match = _DISP_RE.search(disp)
        if match:
            raw = match.group(1).strip()
            # rfc 5987 ext-value: "UTF-8''filename.ext"
            if "''" in raw:
                raw = raw.split("''", 1)[1]
            decoded = email.utils.unquote(unquote(raw))
            cleaned = _UNSAFE.sub("_", decoded).strip()
            if cleaned:
                return cleaned

    parsed = urlparse(url)
    tail = parsed.path.rsplit("/", 1)[-1]
    if tail:
        cleaned = _UNSAFE.sub("_", unquote(tail))
        if cleaned:
            return cleaned

    return "download"
