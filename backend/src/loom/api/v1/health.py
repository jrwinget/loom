import asyncio
from typing import Any

import structlog
from fastapi import APIRouter, Request
from sqlalchemy import text
from temporalio.client import Client

from loom.config import get_settings

router = APIRouter()
log = structlog.get_logger()

EVIDENCE_BUCKET = "loom-evidence"
# short budget so a downed temporal server can't stall load-balancer
# health polls.
TEMPORAL_PROBE_TIMEOUT_S = 2.0


async def _probe_temporal(host: str) -> str:
    """return "ok" if the temporal server accepts a connection."""
    try:
        await asyncio.wait_for(
            Client.connect(host),
            timeout=TEMPORAL_PROBE_TIMEOUT_S,
        )
        return "ok"
    except Exception:
        await log.awarning("temporal health check failed")
        return "error"


@router.get("/health")
async def health_check(request: Request) -> dict[str, Any]:
    """check database, storage, and workflow connectivity."""
    services: dict[str, str] = {}
    settings = get_settings()

    # database check
    try:
        async with request.app.state.db_session_factory() as session:
            await session.execute(text("SELECT 1"))
        services["database"] = "ok"
    except Exception:
        await log.awarning("database health check failed")
        services["database"] = "error"

    # minio / storage check. lite profile uses the local filesystem
    # backend and has no minio client to probe; treat as ok. some
    # test apps leave the attribute unset entirely, so use getattr
    # rather than forcing an AttributeError.
    minio_client = getattr(request.app.state, "minio_client", None)
    if settings.is_lite or minio_client is None:
        services["storage"] = "ok"
    else:
        try:
            minio_client.bucket_exists(EVIDENCE_BUCKET)
            services["storage"] = "ok"
        except Exception:
            await log.awarning("storage health check failed")
            services["storage"] = "error"

    # temporal check. every deployment profile runs workflows — if
    # temporal is unreachable, no evidence can be ingested or
    # exported, so the service is not healthy regardless of db/minio.
    services["temporal"] = await _probe_temporal(settings.temporal_host)

    overall = "ok" if all(v == "ok" for v in services.values()) else "error"

    return {"status": overall, "services": services}
