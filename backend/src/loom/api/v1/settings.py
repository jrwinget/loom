"""runtime app settings — currently the AI engine config.

GET is available to any authenticated user (so the settings ui can
render current state); PUT is admin-only because it changes a global,
egress-affecting setting and stores a secret.
"""

import logging
from collections.abc import AsyncIterator
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from loom.dependencies import get_db_session
from loom.schemas.ai_settings import AiSettingsResponse, AiSettingsUpdate
from loom.security.rbac import require_authenticated
from loom.services.ai_config import AiConfig, load_ai_config, save_ai_config

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/settings", tags=["settings"])


def _to_response(config: AiConfig) -> AiSettingsResponse:
    return AiSettingsResponse(
        transcription_engine=config.transcription_engine,
        api_base_url=config.api_base_url,
        transcription_model=config.transcription_model,
        api_key_set=bool(config.api_key),
    )


@router.get("/ai", response_model=AiSettingsResponse)
async def get_ai_settings(
    token_payload: dict[str, Any] = Depends(  # noqa: B008
        require_authenticated
    ),
    session: AsyncIterator[AsyncSession] = Depends(  # noqa: B008
        get_db_session
    ),
) -> AiSettingsResponse:
    del token_payload
    db: AsyncSession = session  # type: ignore[assignment]
    return _to_response(await load_ai_config(db))


@router.put("/ai", response_model=AiSettingsResponse)
async def update_ai_settings(
    body: AiSettingsUpdate,
    token_payload: dict[str, Any] = Depends(  # noqa: B008
        require_authenticated
    ),
    session: AsyncIterator[AsyncSession] = Depends(  # noqa: B008
        get_db_session
    ),
) -> AiSettingsResponse:
    db: AsyncSession = session  # type: ignore[assignment]
    if token_payload.get("role") != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="admin role required to change ai settings",
        )
    try:
        config = await save_ai_config(db, body.model_dump(exclude_unset=True))
    except ValueError as err:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(err),
        ) from err
    await db.commit()
    return _to_response(config)
