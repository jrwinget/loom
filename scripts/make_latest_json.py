"""build the tauri updater manifest (latest.json) from built bundles.

the in-app updater polls the release feed for this file, compares
versions, and verifies the download against the minisign signature
embedded here. stdlib only, like smoke_sidecar.py, so the CI job
needs no dependency install.

usage:
  python scripts/make_latest_json.py --version v0.2.1 \
      --artifacts-dir artifacts --repo jrwinget/loom --out latest.json
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.parse
from datetime import UTC, datetime
from pathlib import Path

# updater bundle per tauri target triple: (glob, platform key).
# deb is deliberately absent — it cannot self-update; msi is skipped
# in favor of nsis, which tauri recommends for updater flows.
_PLATFORMS = (
    ("*.AppImage", "linux-x86_64"),
    ("*.app.tar.gz", "darwin-aarch64"),
    ("*setup.exe", "windows-x86_64"),
)


def _find_bundle(root: Path, pattern: str) -> Path | None:
    matches = sorted(p for p in root.rglob(pattern) if p.is_file())
    return matches[0] if matches else None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--version", required=True, help="tag, e.g. v0.2.1")
    parser.add_argument("--artifacts-dir", required=True, type=Path)
    parser.add_argument("--repo", required=True, help="owner/name")
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()

    version = args.version.lstrip("v")
    base = (
        f"https://github.com/{args.repo}/releases/download/{args.version}"
    )

    platforms: dict[str, dict[str, str]] = {}
    missing: list[str] = []
    for pattern, key in _PLATFORMS:
        bundle = _find_bundle(args.artifacts_dir, pattern)
        if bundle is None:
            missing.append(f"{key} ({pattern})")
            continue
        sig = bundle.with_name(bundle.name + ".sig")
        if not sig.is_file():
            missing.append(f"{key} signature ({sig.name})")
            continue
        asset = urllib.parse.quote(bundle.name)
        platforms[key] = {
            "signature": sig.read_text().strip(),
            "url": f"{base}/{asset}",
        }

    if missing:
        # a manifest that silently omits a platform strands those
        # installs on the old version forever — fail the job instead
        print(f"FAIL: missing updater artifacts: {', '.join(missing)}")
        return 1

    manifest = {
        "version": version,
        "notes": (
            f"See https://github.com/{args.repo}/releases/tag/"
            f"{args.version} for the full release notes."
        ),
        "pub_date": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "platforms": platforms,
    }
    args.out.write_text(json.dumps(manifest, indent=2) + "\n")
    print(f"OK: wrote {args.out} for {version}: {sorted(platforms)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
