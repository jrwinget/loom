#!/usr/bin/env bash
# boots a throwaway lite-profile backend for playwright e2e runs.
# the smoke spec exercises the first-run flow, so the database and
# data dir must be fresh on every invocation. state lives under a
# fixed tmp path that is wiped at startup rather than on exit —
# playwright may kill the process tree with SIGKILL, so an EXIT trap
# is not reliable.
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
data_dir="${TMPDIR:-/tmp}/loom-e2e-backend"

rm -rf "$data_dir"
mkdir -p "$data_dir"

export LOOM_DEPLOYMENT_PROFILE=lite
export LOOM_DATA_DIR="$data_dir"
export LOOM_DATABASE_URL="sqlite+aiosqlite:///$data_dir/loom.db"
export LOOM_SECRET_KEY="e2e-secret-key-that-is-long-enough-for-tests"
export LOOM_STORAGE_SIGNING_SECRET="e2e-signing-secret-loopback-urls"

# the sidecar entrypoint: bootstraps the sqlite schema exactly like
# the desktop app, then serves on 127.0.0.1:8000
cd "$repo_root/backend"
exec uv run python -m loom
