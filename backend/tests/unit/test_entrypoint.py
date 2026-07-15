"""regression guard for the desktop sidecar entrypoint.

the desktop bundle invokes the pyinstaller-built loom-backend
binary, which runs ``loom.__main__``. v0.1.0 and v0.1.1 shipped
without a server-launching entrypoint: ``main.py`` constructed the
fastapi app and exited without binding a socket, so the desktop
shell hung waiting on /api/v1/health. these tests pin the contract
that the module-level entrypoint actually starts uvicorn against
loom.main:app on 127.0.0.1:8000.
"""

from __future__ import annotations

import runpy
import socket
from typing import Any
from unittest.mock import patch

import pytest


def test_entrypoint_starts_uvicorn_on_localhost_8000() -> None:
    """``python -m loom`` must hand ``loom.main:app`` to uvicorn.

    the desktop shell polls ``http://127.0.0.1:8000/api/v1/health``;
    binding anywhere else (different host, different port) leaves
    the shell waiting on a dead endpoint and the os marks the app
    not-responding. mock uvicorn.run so the test does not actually
    bind a socket.
    """
    captured: dict[str, Any] = {}

    def fake_run(app: Any, **kwargs: Any) -> None:
        captured["app"] = app
        captured.update(kwargs)

    # patching the symbol where it is looked up (loom.__main__)
    # not where it is defined (uvicorn) -- standard mock guidance
    with patch("uvicorn.run", side_effect=fake_run):
        runpy.run_module("loom", run_name="__main__")

    assert captured.get("host") == "127.0.0.1"
    assert captured.get("port") == 8000

    # app must be the asgi callable, not a string import path:
    # pyinstaller --onefile cannot resolve "loom.main:app" strings
    # at runtime because frozen modules disable uvicorn's import
    # machinery. pass the object directly.
    from loom.main import app as expected_app

    assert captured.get("app") is expected_app


def test_port_check_exits_with_sentinel_when_occupied(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """an occupied port must abort before migrations with a marker.

    a stale sidecar holding the port otherwise surfaces as uvicorn's
    bind traceback after the schema work already ran. the sentinel
    line gives the desktop shell (and anyone reading the logs) a
    greppable cause, and exiting early keeps the failed launch cheap.
    """
    from loom.__main__ import _ensure_port_available

    holder = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    holder.bind(("127.0.0.1", 0))
    holder.listen(1)
    port = holder.getsockname()[1]
    try:
        with pytest.raises(SystemExit) as excinfo:
            _ensure_port_available("127.0.0.1", port)
    finally:
        holder.close()

    assert excinfo.value.code == 1
    err = capsys.readouterr().err
    assert "loom-boot-error: port" in err
    assert str(port) in err


def test_port_check_passes_on_free_port() -> None:
    """a free port must not raise or print anything."""
    from loom.__main__ import _ensure_port_available

    probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    probe.bind(("127.0.0.1", 0))
    port = probe.getsockname()[1]
    probe.close()

    _ensure_port_available("127.0.0.1", port)


def test_port_check_tolerates_time_wait_remnants() -> None:
    """sockets in TIME_WAIT must not read as an occupied port.

    a restart right after a shutdown leaves the old server's
    accepted connections in TIME_WAIT on the listen port whenever
    the server side closed first. uvicorn binds with SO_REUSEADDR
    and sails past them; a probe that binds without it is stricter
    than the bind it guards and stochastically kills healthy
    restarts (caught by the two-boot ci smoke).
    """
    from loom.__main__ import _ensure_port_available

    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    listener.bind(("127.0.0.1", 0))
    listener.listen(1)
    port = listener.getsockname()[1]

    client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    client.connect(("127.0.0.1", port))
    server_side, _ = listener.accept()
    # server closes first -> the TIME_WAIT lands on the listen port
    server_side.close()
    client.close()
    listener.close()

    _ensure_port_available("127.0.0.1", port)
