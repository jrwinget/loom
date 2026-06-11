#!/usr/bin/env bash
# bump the project version in all five version-bearing files in
# lockstep: backend/pyproject.toml, frontend/package.json,
# desktop/package.json, desktop/src-tauri/tauri.conf.json, and
# desktop/src-tauri/Cargo.toml. refuses anything that is not plain
# semver so a typo can't fan out to five files.
#
# usage:
#   scripts/bump-version.sh <new-version>
set -euo pipefail

new="${1:-}"
if [[ ! "$new" =~ ^[0-9]+\.[0-9]+\.[0-9]+([.-][a-z0-9]+)*$ ]]; then
    echo "bump-version: '<new-version>' must be semver, got '$new'" >&2
    exit 2
fi

repo_root=$(git rev-parse --show-toplevel)
cd "$repo_root"

old=$(grep -m1 '^version' backend/pyproject.toml \
    | sed -E 's/version *= *"([^"]+)".*/\1/')

# first-match-only edits: every file declares its own version before
# any dependency table, so -m1-style anchored expressions are safe.
sed -i -E "0,/^version = \"$old\"/s//version = \"$new\"/" \
    backend/pyproject.toml \
    desktop/src-tauri/Cargo.toml
sed -i -E "0,/\"version\": \"$old\"/s//\"version\": \"$new\"/" \
    frontend/package.json \
    desktop/package.json \
    desktop/src-tauri/tauri.conf.json

# keep lockfiles' own-package version in step so ci's frozen
# installs don't fail on a stale self-reference.
(cd backend && uv lock --offline >/dev/null 2>&1) || \
    (cd backend && uv lock >/dev/null)
(cd desktop/src-tauri && cargo update --workspace --offline \
    >/dev/null 2>&1) || true

bash scripts/check-version-sync.sh
echo "bumped $old -> $new"
