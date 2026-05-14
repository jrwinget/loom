"""local-only admin endpoints used by the desktop shell.

these endpoints are intentionally NOT in the public api surface. the
single endpoint here today, POST /admin/shutdown, exists so the Tauri
shell can ask the sidecar to terminate cleanly before it falls back
to a hard kill. authentication is a per-launch shared secret passed
through the LOOM_SHUTDOWN_TOKEN env var: the desktop shell mints the
token before spawn, hands it to the sidecar via env, and sends it
back in the X-Loom-Shutdown-Token header on app close.

when the env var is unset (every server-profile deploy and any direct
``loom-backend`` invocation by a developer) the endpoint returns 404
instead of 401, so an external attacker probing the route cannot tell
the surface exists.
"""

from __future__ import annotations

import asyncio
import os
import secrets
from typing import Annotated

from fastapi import APIRouter, Header, HTTPException, status

from loom.config import get_settings

router = APIRouter(prefix="/admin", tags=["admin"])

# how long uvicorn has to finish flushing the 204 before we hard-exit
# the interpreter. 100ms is generous for a localhost roundtrip and
# bounds the worst-case time the operator stares at a closing window.
_EXIT_GRACE_SECONDS = 0.1


def _schedule_exit(delay: float) -> None:
    """schedule ``os._exit(0)`` after ``delay`` seconds on the running loop.

    isolated so tests can patch this single symbol without intercepting
    every ``asyncio.get_running_loop()`` call site (anyio's middleware
    layer also reaches for the loop and expects the real object).
    """
    loop = asyncio.get_running_loop()
    loop.call_later(delay, lambda: os._exit(0))


@router.post(
    "/shutdown",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def shutdown(
    x_loom_shutdown_token: Annotated[
        str | None,
        Header(alias="X-Loom-Shutdown-Token"),
    ] = None,
) -> None:
    """terminate the sidecar process.

    called by the desktop shell on window close. authenticated by a
    per-launch shared secret; absence of the env-configured secret
    masks the endpoint as a 404 to keep the surface invisible on
    server-profile deploys.
    """
    settings = get_settings()
    expected = settings.shutdown_token
    if not expected:
        # endpoint disabled — pretend it doesn't exist so the same
        # response shape applies whether the deploy is configured for
        # local-shutdown or not.
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="not found",
        )

    presented = x_loom_shutdown_token or ""
    if not secrets.compare_digest(presented, expected):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid shutdown token",
        )

    # schedule the exit after uvicorn has had a chance to write the
    # 204 back out. os._exit bypasses atexit handlers and the asyncio
    # loop's shutdown sequence on purpose: the only thing the operator
    # cares about here is that port 8000 is released before the
    # desktop shell respawns the sidecar.
    _schedule_exit(_EXIT_GRACE_SECONDS)
