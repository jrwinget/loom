"""smoke-test the pyinstaller-built loom-backend binary.

usage: ``python smoke_sidecar.py <path-to-binary>``

spawns the binary with the lite-profile env (no minio, no temporal)
and asserts four contracts:

  1. ``GET /api/v1/health`` returns 200 within 60s — guards the
     v0.1.0/v0.1.1 "sidecar never binds a socket" regression,
  2. ``GET /api/v1/first-run/status`` then returns 200 with
     ``{first_run_required: True, deployment_profile: "lite"}``
     — guards the v0.1.3 outage where a fresh install had no
     ``users`` table and the route 500s on ``SELECT COUNT(*)``,
  3. ``OPTIONS /api/v1/auth/login`` with ``Origin: tauri://localhost``
     echoes the origin in ``Access-Control-Allow-Origin`` — guards
     the v0.1.4 leftover where the cors allowlist did not include
     the tauri webview origin so production builds could not log in,
  4. ``POST /first-run/complete`` then ``POST /auth/login`` (with a
     differently-cased email) then ``GET /auth/me`` all succeed —
     guards the lite-only regressions where a case-sensitive email
     lookup rejected the just-created admin and ``/auth/me`` 500'd on
     ``User.id == <jwt sub string>`` under the sqlite uuid binding.
     this is the create-admin-then-sign-back-in flow that surfaced as
     "invalid email or password" after a desktop restart.

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
PREFLIGHT_URL: Final = "http://127.0.0.1:8000/api/v1/auth/login"
COMPLETE_URL: Final = "http://127.0.0.1:8000/api/v1/first-run/complete"
LOGIN_URL: Final = "http://127.0.0.1:8000/api/v1/auth/login"
ME_URL: Final = "http://127.0.0.1:8000/api/v1/auth/me"
# mixed-case on purpose: login must match it case-insensitively.
SMOKE_ADMIN_EMAIL: Final = "Smoke.Admin@Example.com"
SMOKE_ADMIN_PASSWORD: Final = "correct-horse-battery"  # noqa: S105
# webview origin in production tauri 2 on macos/linux. windows uses
# ``http://tauri.localhost``; checking one is sufficient to catch
# allowlist drift because both ride the same config code path.
TAURI_ORIGIN: Final = "tauri://localhost"
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


def _check_preflight_cors() -> tuple[bool, str]:
    """fetch the cors preflight for /auth/login from the tauri webview.

    catches the v0.1.4-class regression where the cors allowlist did
    not cover the tauri webview origin. urllib does not send an
    ``Origin`` header by default, which is why the existing health
    and first-run checks above do not exercise the cors middleware —
    only an explicit ``OPTIONS`` with an ``Origin`` header reproduces
    what the bundled webview does on its first ``fetch()``.

    returns ``(ok, message)``. ``message`` is the failure detail or a
    success summary suitable for logging.
    """
    # PREFLIGHT_URL is a hardcoded http://127.0.0.1 literal -- bandit
    # S310 does not apply.
    req = urllib.request.Request(  # noqa: S310
        PREFLIGHT_URL,
        method="OPTIONS",
        headers={
            "Origin": TAURI_ORIGIN,
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:  # noqa: S310
            allow = resp.headers.get("Access-Control-Allow-Origin", "")
            status_code = resp.status
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        return False, f"HTTP {exc.code} from {PREFLIGHT_URL}: {body}"
    except (urllib.error.URLError, ConnectionError, OSError) as exc:
        return False, f"transport error from {PREFLIGHT_URL}: {exc!r}"

    if status_code != 200:
        return False, (
            f"preflight status {status_code} from {PREFLIGHT_URL} "
            f"(expected 200)"
        )
    if allow != TAURI_ORIGIN:
        return False, (
            f"preflight did not echo {TAURI_ORIGIN!r} in "
            f"Access-Control-Allow-Origin: got {allow!r}"
        )
    return True, (
        f"{PREFLIGHT_URL} OPTIONS -> Access-Control-Allow-Origin={allow!r}"
    )


def _post_json(
    url: str,
    payload: dict[str, str],
    headers: dict[str, str] | None = None,
) -> tuple[int, bytes]:
    """POST a json body and return ``(status, raw)``."""
    data = json.dumps(payload).encode("utf-8")
    hdrs = {"Content-Type": "application/json"}
    if headers:
        hdrs.update(headers)
    # all *_URL constants are hardcoded http://127.0.0.1 literals --
    # bandit S310 does not apply.
    req = urllib.request.Request(  # noqa: S310
        url, data=data, method="POST", headers=hdrs
    )
    with urllib.request.urlopen(req, timeout=5) as resp:  # noqa: S310
        return resp.status, resp.read()


def _check_login_roundtrip() -> tuple[bool, str]:
    """create the bootstrap admin, then sign back in with those creds.

    the desktop shell auto-issues tokens from /first-run/complete, so
    the email+password verify path -- and the token-authenticated
    /auth/me lookup -- runs for the first time only on a *later*
    sign-in. that is when "invalid email or password" surfaced after a
    restart. exercises two lite-only regressions that server-to-server
    postgres tests never saw: a case-sensitive email lookup, and
    /auth/me 500ing on ``User.id == <jwt sub string>`` under sqlite.

    runs last because it mutates state (creates the admin), which would
    flip the /first-run/status contract checked earlier.
    """
    try:
        status, _ = _post_json(
            COMPLETE_URL,
            {
                "admin_email": SMOKE_ADMIN_EMAIL,
                "admin_password": SMOKE_ADMIN_PASSWORD,
                "admin_full_name": "Smoke Admin",
            },
        )
        if status != 201:
            return False, f"first-run/complete -> {status}, expected 201"

        # sign in with a different email casing on purpose.
        status, raw = _post_json(
            LOGIN_URL,
            {
                "email": SMOKE_ADMIN_EMAIL.upper(),
                "password": SMOKE_ADMIN_PASSWORD,
            },
        )
        if status != 200:
            return False, f"login -> {status}, expected 200"
        token = json.loads(raw).get("access_token")
        if not token:
            return False, f"login 200 but no access_token: {raw!r}"

        me_req = urllib.request.Request(  # noqa: S310
            ME_URL,
            method="GET",
            headers={"Authorization": f"Bearer {token}"},
        )
        with urllib.request.urlopen(me_req, timeout=5) as resp:  # noqa: S310
            me_status = resp.status
            me_raw = resp.read()
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        return False, f"HTTP {exc.code} during login round-trip: {body}"
    except (urllib.error.URLError, ConnectionError, OSError) as exc:
        return False, f"transport error during login round-trip: {exc!r}"

    if me_status != 200:
        return False, f"/auth/me -> {me_status}, expected 200"
    me_body = json.loads(me_raw)
    if me_body.get("email") != SMOKE_ADMIN_EMAIL.lower():
        return False, f"/auth/me email not normalized lowercase: {me_body!r}"
    return True, (
        f"first-run/complete -> 201; case-insensitive login -> 200; "
        f"/auth/me -> 200 ({me_body.get('email')!r})"
    )


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

    # ignore_cleanup_errors: on windows the sidecar can still hold the
    # sqlite loom.db handle for a moment after exit, so rmtree on block
    # exit would raise WinError 32 and fail the smoke after it passed.
    with tempfile.TemporaryDirectory(
        prefix="loom-smoke-", ignore_cleanup_errors=True
    ) as tmp:
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
                ok, message = _check_preflight_cors()
                if not ok:
                    print(f"FAIL: {message}")
                    return 1
                print(f"OK: {message}")
                ok, message = _check_login_roundtrip()
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
