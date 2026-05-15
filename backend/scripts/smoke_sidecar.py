"""smoke-test the pyinstaller-built loom-backend binary.

usage: ``python smoke_sidecar.py <path-to-binary>``

spawns the binary with the lite-profile env (no minio, no temporal)
and asserts two contracts:

  1. ``GET /api/v1/health`` returns 200 within 60s — guards the
     v0.1.0/v0.1.1 "sidecar never binds a socket" regression,
  2. ``GET /api/v1/first-run/status`` then returns 200 with
     ``{first_run_required: True, deployment_profile: "lite"}``
     — guards the v0.1.3 outage where a fresh install had no
     ``users`` table and the route 500s on ``SELECT COUNT(*)``.

the 60s health budget matches ``HEALTH_TIMEOUT`` in ``desktop/
src-tauri/src/main.rs``. a sidecar that has not bound a socket
within that window would also fail the desktop shell's own
``wait_for_health`` on startup, so the smoke fails on exactly the
same condition the operator would see. the 60s also covers
pyinstaller --onefile's cold-start unpack on the windows runner,
where defender scans the freshly extracted exe on first launch and
consistently pushes startup into the 15-25s range.

the script is intentionally a single file with only the standard
library so it runs on every os runner without an extra dependency
install step.
"""

from __future__ import annotations

import argparse
import json
import os
import secrets
import signal
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from contextlib import suppress
from pathlib import Path
from typing import Final

HEALTH_URL: Final = "http://127.0.0.1:8000/api/v1/health"
FIRST_RUN_URL: Final = "http://127.0.0.1:8000/api/v1/first-run/status"
POLL_INTERVAL_S: Final = 0.2
DEADLINE_S: Final = 60.0
KILL_GRACE_S: Final = 5.0


def _build_env(data_dir: Path) -> dict[str, str]:
    env = os.environ.copy()
    env.update(
        {
            "LOOM_DEPLOYMENT_PROFILE": "lite",
            "LOOM_DATA_DIR": str(data_dir),
            "LOOM_DATABASE_URL": (
                f"sqlite+aiosqlite:///{data_dir / 'loom.db'}"
            ),
            # 64 hex chars satisfies validate_secret_key() floor
            "LOOM_SECRET_KEY": secrets.token_hex(32),
            "LOOM_STORAGE_SIGNING_SECRET": secrets.token_hex(32),
        }
    )
    return env


def _poll_health() -> bool:
    deadline = time.monotonic() + DEADLINE_S
    while time.monotonic() < deadline:
        # HEALTH_URL is a hardcoded http://127.0.0.1 literal, not user
        # input -- bandit's S310 audit does not apply here.
        with (
            suppress(urllib.error.URLError, ConnectionError, OSError),
            urllib.request.urlopen(HEALTH_URL, timeout=2) as resp,  # noqa: S310
        ):
            if 200 <= resp.status < 300:
                return True
        time.sleep(POLL_INTERVAL_S)
    return False


def _check_first_run_status() -> tuple[bool, str]:
    """fetch /first-run/status and validate the lite-bootstrap contract.

    catches two regressions in one request:
      1. /first-run/status 500s when the schema bootstrap is missing
         (no ``users`` table) — would surface as an exception or non-2xx,
      2. the lite profile env did not reach the sidecar.

    returns ``(ok, message)``. ``message`` is the failure detail or a
    success summary suitable for logging.
    """
    try:
        # FIRST_RUN_URL is a hardcoded http://127.0.0.1 literal -- bandit
        # S310 does not apply.
        with urllib.request.urlopen(  # noqa: S310
            FIRST_RUN_URL, timeout=5
        ) as resp:
            status = resp.status
            raw = resp.read()
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        return False, f"HTTP {exc.code} from {FIRST_RUN_URL}: {body}"
    except (urllib.error.URLError, ConnectionError, OSError) as exc:
        return False, f"transport error from {FIRST_RUN_URL}: {exc!r}"

    if not 200 <= status < 300:
        return False, f"non-2xx status {status} from {FIRST_RUN_URL}"

    try:
        body = json.loads(raw)
    except json.JSONDecodeError as exc:
        return False, f"non-json body from {FIRST_RUN_URL}: {exc}"

    if body.get("first_run_required") is not True:
        return False, (
            f"first_run_required is not True on a fresh install: {body!r}"
        )
    if body.get("deployment_profile") != "lite":
        return False, (
            f"deployment_profile is not 'lite' under smoke env: {body!r}"
        )
    return True, f"{FIRST_RUN_URL} -> 200 {body!r}"


def _terminate(proc: subprocess.Popen[bytes]) -> None:
    if proc.poll() is not None:
        return
    # SIGTERM on posix, CTRL_BREAK_EVENT on windows. fall back to
    # kill() if the process ignores the polite request.
    with suppress(ProcessLookupError, OSError):
        if os.name == "nt":
            proc.send_signal(signal.CTRL_BREAK_EVENT)
        else:
            proc.terminate()
    try:
        proc.wait(timeout=KILL_GRACE_S)
    except subprocess.TimeoutExpired:
        with suppress(ProcessLookupError, OSError):
            proc.kill()
        proc.wait(timeout=KILL_GRACE_S)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "binary",
        type=Path,
        help="path to the pyinstaller-built loom-backend binary",
    )
    args = parser.parse_args()

    if not args.binary.exists():
        print(f"sidecar binary not found: {args.binary}", file=sys.stderr)
        return 2

    with tempfile.TemporaryDirectory(prefix="loom-smoke-") as tmp:
        data_dir = Path(tmp)
        env = _build_env(data_dir)

        creationflags = 0
        if os.name == "nt":
            # CREATE_NEW_PROCESS_GROUP so CTRL_BREAK_EVENT reaches
            # only the sidecar, not the test runner.
            creationflags = subprocess.CREATE_NEW_PROCESS_GROUP

        proc = subprocess.Popen(
            [str(args.binary)],
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            creationflags=creationflags,
        )

        try:
            if _poll_health():
                print(f"OK: {HEALTH_URL} -> 200")
                ok, message = _check_first_run_status()
                if not ok:
                    print(f"FAIL: {message}")
                    return 1
                print(f"OK: {message}")
                return 0

            # if the binary exited on its own, surface its stderr --
            # that is the actionable diagnostic for the v0.1.x bug.
            if proc.poll() is not None:
                out, err = proc.communicate(timeout=KILL_GRACE_S)
                print("FAIL: sidecar exited before serving health")
                print(f"exit code: {proc.returncode}")
                if out:
                    print("--- stdout ---")
                    sys.stdout.buffer.write(out)
                if err:
                    print("--- stderr ---")
                    sys.stderr.buffer.write(err)
                return 1

            print(f"FAIL: {HEALTH_URL} did not answer within {DEADLINE_S:.0f}s")
            return 1
        finally:
            _terminate(proc)


if __name__ == "__main__":
    raise SystemExit(main())
