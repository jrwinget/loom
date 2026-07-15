"""smoke-test the pyinstaller-built loom-backend binary.

usage: ``python smoke_sidecar.py <path-to-binary>``

spawns the binary with the lite-profile env (no minio, no temporal)
and asserts five contracts:

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
     "invalid email or password" after a desktop restart,
  5. ``GET /api/v1/capabilities`` reports the bundled local engines
     — guards the ai-lite pyinstaller collect: a regression there
     builds fine and then reports every engine missing at runtime,
  6. the same binary boots AGAIN after ``alembic_version`` is wound
     back one release — the upgrade branch every existing install
     takes after an update, which the fresh-dir phase never touches
     — and ``/first-run/status`` flips to ``first_run_required:
     False`` and the phase-1 admin can still sign in. this guards
     both the ``_upgrade_lite_schema`` machinery in the frozen
     binary (bundled alembic dir, worker-thread migrate) and the
     replay-safety policy below.

migration replay policy: the upgrade phase rewinds the stamp while
leaving the create_all-built schema in place, so every migration
after ``UPGRADE_REWIND_REVISION`` replays against a database that
already carries the current model state. new migrations must
therefore be idempotent (if_not_exists / inspector guards) or this
smoke fails on the pr that introduces them — which is exactly the
crash a dev-channel install would hit in the wild.

the 60s health budget here is deliberately TIGHTER than the desktop
shell's ``STARTUP_TIMEOUT`` (180s in desktop/src-tauri/src/main.rs).
the shell's ceiling absorbs slow first launches on real hardware —
av sweeps of the onedir tree, slow disks — where waiting longer
genuinely helps. ci runners have fast disks, so a sidecar that
needs more than 60s here is a cold-start perf regression worth
failing on, long before users hit the shell's ceiling: a onedir
boot is seconds, so a budget blowout here most likely means the
packaging regressed to something that unpacks per launch.

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
import sqlite3
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from contextlib import suppress
from pathlib import Path
from typing import Final

HEALTH_URL: Final = "http://127.0.0.1:8000/api/v1/health"
OPENAPI_URL: Final = "http://127.0.0.1:8000/openapi.json"
FIRST_RUN_URL: Final = "http://127.0.0.1:8000/api/v1/first-run/status"
PREFLIGHT_URL: Final = "http://127.0.0.1:8000/api/v1/auth/login"
COMPLETE_URL: Final = "http://127.0.0.1:8000/api/v1/first-run/complete"
LOGIN_URL: Final = "http://127.0.0.1:8000/api/v1/auth/login"
ME_URL: Final = "http://127.0.0.1:8000/api/v1/auth/me"
CAPABILITIES_URL: Final = "http://127.0.0.1:8000/api/v1/capabilities"
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
# the release-before-current head. the upgrade phase winds the stamp
# back here and boots again, so every migration after this revision
# replays against the create_all schema (see the module docstring's
# replay policy). bump alongside new migrations once they have
# shipped in a release.
UPGRADE_REWIND_REVISION: Final = "017"


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


def _check_reported_version() -> tuple[bool, str]:
    """assert the frozen binary reports the packaged version.

    pyinstaller must carry the loom dist-info into the bundle
    (``--copy-metadata loom``); without it importlib.metadata falls
    back to "0.0.0+dev" and the app misreports its version in the
    openapi doc and telemetry.
    """
    try:
        # OPENAPI_URL is a hardcoded http://127.0.0.1 literal -- bandit
        # S310 does not apply.
        with urllib.request.urlopen(  # noqa: S310
            OPENAPI_URL, timeout=5
        ) as resp:
            body = json.loads(resp.read())
    except (urllib.error.URLError, ConnectionError, OSError) as exc:
        return False, f"transport error from {OPENAPI_URL}: {exc!r}"
    reported = str(body.get("info", {}).get("version", ""))
    if reported in ("", "0.0.0+dev", "0.1.0"):
        return False, (
            f"frozen binary reports version {reported!r} — the loom "
            "dist-info is missing from the bundle (--copy-metadata)"
        )
    return True, f"reported version {reported}"


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


def _check_capabilities() -> tuple[bool, str]:
    """the bundled sidecar must report its local engines available.

    guards the ai-lite bundling: a pyinstaller collect regression
    would build fine and then report every engine missing at runtime.
    ocr and media_pipeline also need host binaries (tesseract,
    ffmpeg) the runner may lack, so only the pure-python engines are
    asserted. runs after the login round-trip, which creates the
    admin whose credentials it reuses.
    """
    try:
        status, raw = _post_json(
            LOGIN_URL,
            {
                "email": SMOKE_ADMIN_EMAIL,
                "password": SMOKE_ADMIN_PASSWORD,
            },
        )
        if status != 200:
            return False, f"capabilities login -> {status}, expected 200"
        token = json.loads(raw).get("access_token")
        if not token:
            return False, f"capabilities login without token: {raw!r}"

        req = urllib.request.Request(  # noqa: S310
            CAPABILITIES_URL,
            method="GET",
            headers={"Authorization": f"Bearer {token}"},
        )
        with urllib.request.urlopen(req, timeout=5) as resp:  # noqa: S310
            cap_status = resp.status
            body = json.loads(resp.read())
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        return False, f"HTTP {exc.code} fetching capabilities: {detail}"
    except (urllib.error.URLError, ConnectionError, OSError) as exc:
        return False, f"transport error fetching capabilities: {exc!r}"

    if cap_status != 200:
        return False, f"/capabilities -> {cap_status}, expected 200"
    engines = body.get("engines") or {}

    scene = engines.get("scene_detection") or {}
    if scene.get("status") != "available":
        return False, f"scene_detection missing from bundle: {engines!r}"

    # a fresh sidecar has no whisper weights, so transcription_local
    # legitimately reports missing — but its remedy must be the
    # download-a-model one. the not-installed remedy means the engine
    # import itself failed, i.e. the bundle collect regressed.
    trans = engines.get("transcription_local") or {}
    if trans.get("status") != "available":
        remedy = str(trans.get("remedy") or "")
        if "model" not in remedy:
            return False, (
                f"transcription engine absent from bundle: {trans!r}"
            )
    return True, (
        "bundled engines: scene_detection available; "
        f"transcription_local {trans.get('status')} "
        f"({trans.get('remedy') or 'ready'})"
    )


def _read_alembic_stamp(db_path: Path) -> str:
    conn = sqlite3.connect(db_path, timeout=5)
    try:
        row = conn.execute("SELECT version_num FROM alembic_version").fetchone()
    finally:
        conn.close()
    if row is None:
        raise RuntimeError("alembic_version table has no row")
    return str(row[0])


def _rewind_alembic_stamp(db_path: Path, revision: str) -> None:
    """wind the stamp back so the next boot takes the upgrade branch.

    retried because on windows the just-terminated sidecar can hold
    the sqlite file handle for a moment (same lag the tempdir cleanup
    works around with ignore_cleanup_errors).
    """
    deadline = time.monotonic() + KILL_GRACE_S * 2
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        try:
            conn = sqlite3.connect(db_path, timeout=1)
            try:
                conn.execute(
                    "UPDATE alembic_version SET version_num = ?",
                    (revision,),
                )
                conn.commit()
                return
            finally:
                conn.close()
        except sqlite3.OperationalError as exc:
            last_error = exc
            time.sleep(0.5)
    raise RuntimeError(f"could not rewind alembic stamp: {last_error!r}")


def _check_upgraded_first_run() -> tuple[bool, str]:
    """after the upgrade boot, the phase-1 admin must still exist."""
    try:
        # FIRST_RUN_URL is a hardcoded http://127.0.0.1 literal --
        # bandit S310 does not apply.
        with urllib.request.urlopen(  # noqa: S310
            FIRST_RUN_URL, timeout=5
        ) as resp:
            body = json.loads(resp.read())
    except (urllib.error.URLError, ConnectionError, OSError) as exc:
        return False, f"transport error from {FIRST_RUN_URL}: {exc!r}"
    if body.get("first_run_required") is not False:
        return False, (
            "first_run_required should be False after the upgrade "
            f"boot (existing admin): {body!r}"
        )
    return True, f"upgrade boot: {FIRST_RUN_URL} -> {body!r}"


def _check_login_after_upgrade() -> tuple[bool, str]:
    """the pre-upgrade admin signs in against the migrated database.

    this is the flow a real install runs after every app update, and
    the one the fresh-dir phase can never cover: existing user,
    existing schema, migrations replayed on top.
    """
    try:
        status, raw = _post_json(
            LOGIN_URL,
            {
                "email": SMOKE_ADMIN_EMAIL,
                "password": SMOKE_ADMIN_PASSWORD,
            },
        )
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        return False, f"HTTP {exc.code} on post-upgrade login: {body}"
    except (urllib.error.URLError, ConnectionError, OSError) as exc:
        return False, f"transport error on post-upgrade login: {exc!r}"
    if status != 200:
        return False, f"post-upgrade login -> {status}, expected 200"
    if not json.loads(raw).get("access_token"):
        return False, f"post-upgrade login 200 without token: {raw!r}"
    return True, "upgrade boot: existing admin login -> 200"


def _spawn_sidecar(
    binary: Path,
    env: dict[str, str],
    creationflags: int,
) -> subprocess.Popen[bytes]:
    return subprocess.Popen(
        [str(binary)],
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        creationflags=creationflags,
    )


def _fail_dead_or_timeout(proc: subprocess.Popen[bytes]) -> int:
    """diagnose a boot that never served health; returns exit code 1.

    if the binary exited on its own, surface its stderr — that is
    the actionable diagnostic for the v0.1.x class of bug.
    """
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


def _run_checks(
    checks: tuple[Callable[[], tuple[bool, str]], ...],
) -> bool:
    for check in checks:
        ok, message = check()
        if not ok:
            print(f"FAIL: {message}")
            return False
        print(f"OK: {message}")
    return True


def _verify_stamp_advanced(db_path: Path) -> bool:
    stamp = _read_alembic_stamp(db_path)
    if stamp == UPGRADE_REWIND_REVISION:
        print(
            f"FAIL: stamp still {stamp!r} after the upgrade boot — "
            "_upgrade_lite_schema did not run"
        )
        return False
    print(f"OK: upgrade boot advanced the stamp to {stamp!r}")
    return True


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


def _force_utf8_output() -> None:
    """windows runners default stdout to cp1252, which cannot encode
    the arrows in engine remedy strings the capabilities check
    prints — reconfigure rather than sanitize every message."""
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")


def main() -> int:
    _force_utf8_output()
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

        proc = _spawn_sidecar(args.binary, env, creationflags)
        try:
            if not _poll_health():
                return _fail_dead_or_timeout(proc)
            print(f"OK: {HEALTH_URL} -> 200")
            fresh_checks = (
                _check_first_run_status,
                _check_preflight_cors,
                _check_login_roundtrip,
                _check_capabilities,
                _check_reported_version,
            )
            if not _run_checks(fresh_checks):
                return 1

            # upgrade phase: same binary, same data dir, stamp wound
            # back one release — the boot path every existing install
            # takes after an update.
            _terminate(proc)
            db_path = data_dir / "loom.db"
            _rewind_alembic_stamp(db_path, UPGRADE_REWIND_REVISION)
            print(
                f"OK: stamp rewound to {UPGRADE_REWIND_REVISION}; "
                "booting again for the upgrade phase"
            )
            proc = _spawn_sidecar(args.binary, env, creationflags)
            if not _poll_health():
                return _fail_dead_or_timeout(proc)
            print(f"OK: upgrade boot {HEALTH_URL} -> 200")
            upgrade_checks = (
                _check_upgraded_first_run,
                _check_login_after_upgrade,
            )
            if not _run_checks(upgrade_checks):
                return 1
            if not _verify_stamp_advanced(db_path):
                return 1
            return 0
        finally:
            _terminate(proc)


if __name__ == "__main__":
    raise SystemExit(main())
