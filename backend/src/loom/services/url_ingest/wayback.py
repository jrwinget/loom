"""Wayback Machine snapshot helper (non-blocking)."""

import logging

logger = logging.getLogger(__name__)

try:
    import savepagenow

    _AVAILABLE = True
except ImportError:
    _AVAILABLE = False


def is_available() -> bool:
    """Return True when savepagenow is importable."""
    return _AVAILABLE


def snapshot_url(url: str, timeout: int = 30) -> str | None:
    """Request a Wayback snapshot; return the archive URL or None.

    Non-blocking: any failure (missing dep, network error, 429
    throttle, timeout, unexpected response) is logged at WARNING
    level and returns None. Callers must treat None as "snapshot
    not available right now" — never as a fatal error.
    """
    if not _AVAILABLE:
        logger.warning("savepagenow not installed; skipping wayback snapshot")
        return None

    try:
        archive_url = savepagenow.capture(url, timeout=timeout)
    except Exception as exc:
        # broad catch is intentional — wayback is best-effort
        logger.warning(
            "wayback snapshot failed for %s: %s",
            url,
            exc,
        )
        return None

    if not archive_url:
        logger.warning(
            "wayback snapshot returned empty URL for %s",
            url,
        )
        return None
    return str(archive_url)
