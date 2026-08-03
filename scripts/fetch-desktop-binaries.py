"""fetch and verify the pinned host binaries for the desktop bundle.

reads desktop/binaries.lock.json and materialises the entries for one
platform into desktop/src-tauri/binaries/, which tauri ships as a
resource directory. every download is verified against its pinned
sha256 before anything lands in the bundle — a mismatch fails the
build rather than shipping an unverified binary. stdlib only, like
the sibling scripts, so CI needs no dependency install.

usage:
  python scripts/fetch-desktop-binaries.py --platform linux
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import stat
import sys
import tarfile
import tempfile
import urllib.request
import zipfile
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent
_LOCKFILE = _REPO / "desktop" / "binaries.lock.json"
_DEST = _REPO / "desktop" / "src-tauri" / "binaries"

_PLATFORM_KEYS = {
    "linux": "linux-x86_64",
    "windows": "windows-x86_64",
    "macos": "macos-aarch64",
}


def _download_verified(url: str, sha256: str, dest: Path) -> None:
    digest = hashlib.sha256()
    try:
        # the url comes from the checked-in lockfile, not user input
        with (
            urllib.request.urlopen(url, timeout=600) as resp,  # noqa: S310
            dest.open("wb") as fh,
        ):
            while chunk := resp.read(1024 * 1024):
                fh.write(chunk)
                digest.update(chunk)
    except OSError as err:
        # name the url — a bare HTTPError traceback hides which
        # pinned entry rotted
        raise SystemExit(f"FAIL: {url}\n  {err}") from err
    actual = digest.hexdigest()
    if actual != sha256:
        raise SystemExit(
            f"FAIL: {url}\n  expected sha256 {sha256}\n  got      {actual}"
        )


def _extract_binaries(
    archive: Path, kind: str, names: list[str], dest_dir: Path
) -> None:
    """pull just the named binaries out of an archive, flat."""
    with tempfile.TemporaryDirectory() as tmp:
        if kind == "tar":
            with tarfile.open(archive) as tf:
                tf.extractall(tmp, filter="data")
        elif kind == "zip":
            with zipfile.ZipFile(archive) as zf:
                zf.extractall(tmp)
        else:
            raise SystemExit(f"FAIL: unknown extract kind {kind!r}")
        for name in names:
            matches = sorted(Path(tmp).rglob(name))
            if not matches:
                raise SystemExit(f"FAIL: {name} not found in {archive.name}")
            target = dest_dir / name
            shutil.copy2(matches[0], target)
            target.chmod(target.stat().st_mode | stat.S_IEXEC)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--platform", required=True, choices=sorted(_PLATFORM_KEYS)
    )
    args = parser.parse_args()
    key = _PLATFORM_KEYS[args.platform]

    lock = json.loads(_LOCKFILE.read_text())
    _DEST.mkdir(parents=True, exist_ok=True)

    fetched: list[str] = []
    for tool in ("ffmpeg", "tesseract"):
        entry = lock.get(tool, {}).get(key)
        if entry is None:
            print(f"skip: no pinned {tool} for {key}")
            continue
        with tempfile.NamedTemporaryFile(delete=False) as tmp:
            tmp_path = Path(tmp.name)
        try:
            _download_verified(entry["url"], entry["sha256"], tmp_path)
            if entry["extract"] == "none":
                target = _DEST / entry["binaries"][0]
                shutil.copy2(tmp_path, target)
                target.chmod(target.stat().st_mode | stat.S_IEXEC)
            else:
                _extract_binaries(
                    tmp_path, entry["extract"], entry["binaries"], _DEST
                )
            fetched.extend(entry["binaries"])
        finally:
            tmp_path.unlink(missing_ok=True)

    tessdata = lock.get("tessdata", {})
    if tessdata and key != "macos-aarch64":
        data_dir = _DEST / "tessdata"
        data_dir.mkdir(exist_ok=True)
        for lang, entry in tessdata.items():
            dest = data_dir / f"{lang}.traineddata"
            _download_verified(entry["url"], entry["sha256"], dest)
            fetched.append(dest.name)

    print(f"OK: fetched for {key}: {fetched or 'nothing (by design)'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
