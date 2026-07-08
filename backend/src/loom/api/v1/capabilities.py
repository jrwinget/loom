"""install capability reporting.

the frontend has no other way to know which processing engines this
install can actually run, so it renders buttons for jobs doomed to
fail. this endpoint feeds that gating. /health stays untouched — it
is an unauthenticated load-balancer probe, not a feature-flag
surface.
"""

from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from loom.config import get_settings
from loom.security.rbac import require_authenticated
from loom.services.engines import probe_engines

router = APIRouter(tags=["capabilities"])


class EngineCapability(BaseModel):
    status: str
    remedy: str | None = None
    version: str | None = None


class CapabilitiesResponse(BaseModel):
    profile: str
    engines: dict[str, EngineCapability]


@router.get("/capabilities", response_model=CapabilitiesResponse)
async def get_capabilities(
    _token_payload: dict[str, Any] = Depends(  # noqa: B008
        require_authenticated
    ),
) -> CapabilitiesResponse:
    """report which engines this install can run, with remedies."""
    settings = get_settings()
    probed = probe_engines()
    engines = {
        name: EngineCapability(
            status=state.status,
            remedy=state.remedy,
            version=state.version,
        )
        for name, state in probed.items()
    }
    # cloud transcription is config-driven, not binary-driven: it is
    # available whenever an endpoint is reachable, which the settings
    # page owns. report it as available so the ui offers the cloud
    # path when the local engine is missing.
    engines["transcription_cloud"] = EngineCapability(status="available")
    return CapabilitiesResponse(
        profile=settings.deployment_profile,
        engines=engines,
    )
