from typing import Any

import structlog
from fastapi import APIRouter, Request
from sqlalchemy import text

router = APIRouter()
log = structlog.get_logger()

EVIDENCE_BUCKET = "loom-evidence"


@router.get("/health")
async def health_check(request: Request) -> dict[str, Any]:
    """check database and storage connectivity."""
    services: dict[str, str] = {}

    # database check
    try:
        async with request.app.state.db_session_factory() as session:
            await session.execute(text("SELECT 1"))
        services["database"] = "ok"
    except Exception:
        await log.awarning("database health check failed")
        services["database"] = "error"

    # minio / storage check
    try:
        minio_client = request.app.state.minio_client
        minio_client.bucket_exists(EVIDENCE_BUCKET)
        services["storage"] = "ok"
    except Exception:
        await log.awarning("storage health check failed")
        services["storage"] = "error"

    overall = "ok" if all(v == "ok" for v in services.values()) else "error"

    return {"status": overall, "services": services}
