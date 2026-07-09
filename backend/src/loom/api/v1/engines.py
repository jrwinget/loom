"""engine status and whisper model management.

the capabilities endpoint says what an install can run; this router
is where the operator acts on it: inspect engines, download a
pinned whisper model (the only egress, admin-only, explicit), watch
its progress, and delete it. download state is process-local like
the lite job map — a restart forgets an in-flight download, and the
partial-directory scheme in the registry makes that safe.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from loom.security.rbac import require_authenticated, require_role
from loom.services import model_registry
from loom.services.engines import probe_engines
from loom.services.model_registry import WHISPER_MODELS

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/settings/engines", tags=["settings"])

# module-level singleton so the dependency factory call sits outside
# argument defaults (B008); one instance serves every admin route
_require_admin = require_role("admin")


@dataclass
class DownloadState:
    status: str  # "downloading" | "complete" | "failed"
    bytes_done: int = 0
    bytes_total: int = 0
    error: str | None = None


_DOWNLOADS: dict[str, DownloadState] = {}
# strong refs so the event loop cannot garbage-collect a running
# download task; entries are replaced on redownload, never awaited
_TASKS: dict[str, asyncio.Task[None]] = {}


def _model_entry(name: str) -> dict[str, Any]:
    spec = WHISPER_MODELS[name]
    state = _DOWNLOADS.get(name)
    return {
        "name": name,
        "size_bytes": spec.total_bytes,
        "downloaded": model_registry.is_downloaded(name),
        "download_status": state.status if state else None,
        "bytes_done": state.bytes_done if state else None,
        "bytes_total": state.bytes_total if state else None,
        "error": state.error if state else None,
    }


@router.get("")
async def engine_status(
    token_payload: dict[str, Any] = Depends(  # noqa: B008
        require_authenticated
    ),
) -> dict[str, Any]:
    """probe results plus the whisper model catalog with local state."""
    engines = {
        name: {
            "status": status.status,
            "remedy": status.remedy,
            "version": status.version,
        }
        for name, status in probe_engines().items()
    }
    models = [_model_entry(name) for name in WHISPER_MODELS]
    return {"engines": engines, "models": models}


async def _run_download(name: str) -> None:
    state = _DOWNLOADS[name]

    def on_progress(done: int, total: int) -> None:
        state.bytes_done = done
        state.bytes_total = total

    try:
        await model_registry.download_model(name, on_progress=on_progress)
        state.status = "complete"
    except Exception as exc:
        logger.warning("model download failed: %s", exc)
        state.status = "failed"
        state.error = str(exc)


@router.post("/models/{name}/download", status_code=202)
async def download_model(
    name: str,
    token_payload: dict[str, Any] = Depends(  # noqa: B008
        _require_admin
    ),
) -> dict[str, Any]:
    """start an explicit model download; poll the status endpoint.

    the one deliberate egress on the desktop profile — admin-only
    and never implicit. 202 with the initial state; idempotent for
    an already-downloaded or already-downloading model.
    """
    if name not in WHISPER_MODELS:
        raise HTTPException(status_code=404, detail="unknown model")

    existing = _DOWNLOADS.get(name)
    if existing is not None and existing.status == "downloading":
        return _model_entry(name)
    if model_registry.is_downloaded(name):
        _DOWNLOADS.pop(name, None)
        return _model_entry(name)

    spec = WHISPER_MODELS[name]
    _DOWNLOADS[name] = DownloadState(
        status="downloading", bytes_total=spec.total_bytes
    )
    _TASKS[name] = asyncio.create_task(_run_download(name))
    return _model_entry(name)


@router.get("/models/{name}/status")
async def model_status(
    name: str,
    token_payload: dict[str, Any] = Depends(  # noqa: B008
        require_authenticated
    ),
) -> dict[str, Any]:
    if name not in WHISPER_MODELS:
        raise HTTPException(status_code=404, detail="unknown model")
    return _model_entry(name)


@router.delete("/models/{name}", status_code=204)
async def delete_model(
    name: str,
    token_payload: dict[str, Any] = Depends(  # noqa: B008
        _require_admin
    ),
) -> None:
    if name not in WHISPER_MODELS:
        raise HTTPException(status_code=404, detail="unknown model")
    state = _DOWNLOADS.get(name)
    if state is not None and state.status == "downloading":
        raise HTTPException(
            status_code=409, detail="model is currently downloading"
        )
    _DOWNLOADS.pop(name, None)
    model_registry.delete_model(name)
