#!/usr/bin/env bash
# verify that all five version-bearing files agree, and that a
# release/* branch name matches that version. used by the pre-push
# hook and the Verify Versions ci job so a release can never ship
# with the desktop app, backend, and frontend disagreeing about
# what version they are.
#
# usage:
#   scripts/check-version-sync.sh [branch-name]
#
# the branch argument is optional; without it only file lockstep is
# checked. returns non-zero on any mismatch.
set -euo pipefail

repo_root=$(git rev-parse --show-toplevel)
cd "$repo_root"

backend=$(grep -m1 '^version' backend/pyproject.toml \
    | sed -E 's/version *= *"([^"]+)".*/\1/')
frontend=$(grep -m1 '"version"' frontend/package.json \
    | sed -E 's/.*"version" *: *"([^"]+)".*/\1/')
desktop=$(grep -m1 '"version"' desktop/package.json \
    | sed -E 's/.*"version" *: *"([^"]+)".*/\1/')
tauri_conf=$(grep -m1 '"version"' desktop/src-tauri/tauri.conf.json \
    | sed -E 's/.*"version" *: *"([^"]+)".*/\1/')
cargo=$(grep -m1 '^version' desktop/src-tauri/Cargo.toml \
    | sed -E 's/version *= *"([^"]+)".*/\1/')

mismatch=0
for pair in \
    "frontend/package.json:$frontend" \
    "desktop/package.json:$desktop" \
    "desktop/src-tauri/tauri.conf.json:$tauri_conf" \
    "desktop/src-tauri/Cargo.toml:$cargo"; do
    file="${pair%%:*}"
    found="${pair#*:}"
    if [[ "$found" != "$backend" ]]; then
        echo "check-version-sync: $file has '$found' but" \
            "backend/pyproject.toml has '$backend'" >&2
        mismatch=1
    fi
done
if [[ "$mismatch" -ne 0 ]]; then
    echo "  run scripts/bump-version.sh <version> to realign." >&2
    exit 1
fi

branch="${1:-}"
if [[ "$branch" =~ ^release/v?(.+)$ ]]; then
    branch_version="${BASH_REMATCH[1]}"
    if [[ "$branch_version" != "$backend" ]]; then
        echo "check-version-sync: version '$backend' does not match" \
            "branch '$branch' (expected '$branch_version')" >&2
        echo "  run scripts/bump-version.sh $branch_version" \
            "before pushing this release branch." >&2
        exit 1
    fi
fi

echo "version sync ok: $backend"
