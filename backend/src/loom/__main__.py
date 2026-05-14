"""server entrypoint for the desktop sidecar.

separated from ``loom.main`` (the asgi factory) so that the docker
image and ``make dev`` can keep importing ``loom.main:app`` directly
while pyinstaller bundles this file as the binary's ``__main__``.
the desktop shell at desktop/src-tauri/src/main.rs polls
``http://127.0.0.1:8000/api/v1/health`` after spawning the sidecar,
so the host/port pair below is load-bearing -- changing it without
updating the rust side leaves the shell waiting on a dead endpoint.

passing the asgi callable as an object (not the ``loom.main:app``
import string) is deliberate: pyinstaller --onefile freezes the
module graph and uvicorn's string-import resolution does not
survive that, while a direct reference does.
"""

from __future__ import annotations

import os
import sys
import threading
import time

import uvicorn

from loom.main import app

# how often the orphan watchdog polls getppid(). 1s is fast enough
# that the operator never sees a stale port-bind error on the next
# launch and slow enough to stay invisible in process listings.
_WATCHDOG_INTERVAL_SECONDS = 1.0


def _start_orphan_watchdog() -> None:
    """exit when the parent process dies.

    pyinstaller --onefile spawns the python interpreter as a child of
    a small bootloader. when the tauri shell calls ``child.kill()``
    against the externalBin it terminates the bootloader; the python
    process is orphaned (reparented to pid 1 on unix) and continues
    to hold ``127.0.0.1:8000``, blocking the next launch.

    this thread catches that case by polling ``os.getppid()`` and
    exiting when the original parent goes away. it is gated on
    ``LOOM_SHUTDOWN_TOKEN`` being set, which the desktop shell does
    on every launch — direct invocations (``nohup loom-backend &``,
    systemd, ``make dev``) get the env unset and skip the watchdog,
    so a backgrounded server doesn't self-terminate when its launching
    shell exits.

    windows installs are covered by the job-object the rust side
    attaches to the bootloader pid, so the watchdog is a unix-only
    safety net.
    """
    if sys.platform == "win32":
        return
    if not os.environ.get("LOOM_SHUTDOWN_TOKEN"):
        return

    initial_ppid = os.getppid()
    if initial_ppid <= 1:
        # already orphaned at startup (rare; e.g. a debugger launch)
        # — installing the watchdog would just exit immediately. let
        # the operator keep the process they meant to start.
        return

    def _watch() -> None:
        while True:
            time.sleep(_WATCHDOG_INTERVAL_SECONDS)
            current = os.getppid()
            if current == 1 or current != initial_ppid:
                # parent died — release port 8000 so the desktop
                # shell can respawn cleanly on the next launch.
                os._exit(0)

    thread = threading.Thread(
        target=_watch,
        daemon=True,
        name="loom-orphan-watchdog",
    )
    thread.start()


def main() -> None:
    _start_orphan_watchdog()
    uvicorn.run(
        app,
        host="127.0.0.1",
        port=8000,
        log_config=None,
    )


if __name__ == "__main__":
    main()
