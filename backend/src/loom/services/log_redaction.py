"""structlog processor that scrubs pii from lite-profile log lines.

desktop-lite log lines persist on disk and travel inside
diagnostics zips (issues #285/#286), so anything identifying —
account emails, home-directory paths that embed the os username —
is replaced at write time. the server profile never loads this
processor; its stdout logging stays byte-identical.
"""

from __future__ import annotations

import re
from pathlib import Path

from structlog.typing import EventDict, WrappedLogger

_REDACTED_EMAIL = "<redacted-email>"

_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")


def _home_patterns() -> tuple[re.Pattern[str], ...]:
    """prefixes that leak an os username; each is replaced with ~."""
    patterns = [
        # generic linux/macos/windows home prefixes cover other
        # users' paths surfacing in configs or tracebacks. quote
        # chars end the username so embedded json stays intact.
        r"/home/[^/\\\s\"']+",
        r"/Users/[^/\\\s\"']+",
        r"[A-Za-z]:[\\/]Users[\\/][^\\/\s\"']+",
    ]
    # the running user's home first, so non-standard locations
    # (e.g. /root, /var/users/x) are caught too.
    home = str(Path.home())
    if len(home) > 1:
        patterns.insert(0, re.escape(home))
    return tuple(re.compile(p) for p in patterns)


_HOME_PATTERNS = _home_patterns()


def _redact_text(text: str) -> str:
    text = _EMAIL_RE.sub(_REDACTED_EMAIL, text)
    for pattern in _HOME_PATTERNS:
        text = pattern.sub("~", text)
    return text


def _redact_value(value: object) -> object:
    if isinstance(value, str):
        return _redact_text(value)
    if isinstance(value, dict):
        return {key: _redact_value(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_redact_value(item) for item in value]
    if isinstance(value, tuple):
        return tuple(_redact_value(item) for item in value)
    return value


def redact_sensitive(
    _logger: WrappedLogger,
    _method: str,
    event_dict: EventDict,
) -> EventDict:
    """replace emails and home paths in every string value."""
    for key, value in event_dict.items():
        event_dict[key] = _redact_value(value)
    return event_dict
