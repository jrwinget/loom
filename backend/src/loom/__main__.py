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

import uvicorn

from loom.main import app


def main() -> None:
    uvicorn.run(
        app,
        host="127.0.0.1",
        port=8000,
        log_config=None,
    )


if __name__ == "__main__":
    main()
