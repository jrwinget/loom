"""the app must report the installed package version, not a literal.

two hardcoded "0.1.0" strings survived every release because the
bump script only rewrites the five packaging files; deriving the
runtime version from package metadata makes drift impossible.
"""

from importlib.metadata import version
from pathlib import Path

import loom

_SRC = Path(__file__).resolve().parents[2] / "src" / "loom"


def test_dunder_version_matches_installed_dist() -> None:
    assert loom.__version__ == version("loom")


def test_no_hardcoded_version_literals_in_source() -> None:
    offenders = [
        path
        for path in _SRC.rglob("*.py")
        if 'version="0.1' in path.read_text(encoding="utf-8")
        or "version': '0.1" in path.read_text(encoding="utf-8")
    ]
    assert offenders == []
