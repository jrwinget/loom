populated at build time by scripts/fetch-desktop-binaries.py from
the pinned, sha256-verified entries in desktop/binaries.lock.json.
this placeholder keeps the tauri resource glob valid on platforms
with no bundled binaries (macos probes homebrew instead).
see desktop/THIRD-PARTY-BINARIES.md for licenses.
