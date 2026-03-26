from collections.abc import AsyncIterator
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from loom.dependencies import get_db_session
from loom.schemas.plugin import (
    PluginCreate,
    PluginListResponse,
    PluginResponse,
    PluginUpdate,
    WebhookCreate,
    WebhookDeliveryListResponse,
    WebhookDeliveryResponse,
    WebhookListResponse,
    WebhookResponse,
    WebhookUpdate,
)
from loom.security.rbac import (
    get_current_user_id,
    require_authenticated,
    require_role,
)
from loom.services.plugin import (
    create_plugin,
    delete_plugin,
    get_plugin,
    list_plugins,
    update_plugin,
)
from loom.services.webhook import (
    create_webhook,
    delete_webhook,
    get_deliveries,
    get_webhook,
    list_webhooks,
    update_webhook,
)

_admin_dep = require_role("admin")

router = APIRouter(
    prefix="/plugins",
    tags=["plugins"],
)


@router.post(
    "",
    response_model=PluginResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_plugin_endpoint(
    body: PluginCreate,
    token_payload: dict[str, Any] = Depends(  # noqa: B008
        _admin_dep
    ),
    session: AsyncIterator[AsyncSession] = Depends(  # noqa: B008
        get_db_session
    ),
) -> PluginResponse:
    """create a plugin (admin only)."""
    db: AsyncSession = session  # type: ignore[assignment]
    user_id = get_current_user_id(token_payload)
    data = body.model_dump()
    plugin = await create_plugin(db, data, user_id)
    return PluginResponse.model_validate(plugin)


@router.get("", response_model=PluginListResponse)
async def list_plugins_endpoint(
    plugin_type: str | None = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    token_payload: dict[str, Any] = Depends(  # noqa: B008
        require_authenticated
    ),
    session: AsyncIterator[AsyncSession] = Depends(  # noqa: B008
        get_db_session
    ),
) -> PluginListResponse:
    """list plugins (any authenticated user)."""
    db: AsyncSession = session  # type: ignore[assignment]
    plugins, total = await list_plugins(db, plugin_type, skip, limit)
    items = [PluginResponse.model_validate(p) for p in plugins]
    return PluginListResponse(items=items, total=total)


@router.get(
    "/{plugin_id}",
    response_model=PluginResponse,
)
async def get_plugin_endpoint(
    plugin_id: str,
    token_payload: dict[str, Any] = Depends(  # noqa: B008
        require_authenticated
    ),
    session: AsyncIterator[AsyncSession] = Depends(  # noqa: B008
        get_db_session
    ),
) -> PluginResponse:
    """get plugin detail."""
    db: AsyncSession = session  # type: ignore[assignment]
    plugin = await get_plugin(db, plugin_id)
    if not plugin:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="plugin not found",
        )
    return PluginResponse.model_validate(plugin)


@router.patch(
    "/{plugin_id}",
    response_model=PluginResponse,
)
async def update_plugin_endpoint(
    plugin_id: str,
    body: PluginUpdate,
    token_payload: dict[str, Any] = Depends(  # noqa: B008
        _admin_dep
    ),
    session: AsyncIterator[AsyncSession] = Depends(  # noqa: B008
        get_db_session
    ),
) -> PluginResponse:
    """update a plugin (admin only)."""
    db: AsyncSession = session  # type: ignore[assignment]
    existing = await get_plugin(db, plugin_id)
    if not existing:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="plugin not found",
        )
    data = body.model_dump(exclude_unset=True)
    plugin = await update_plugin(db, plugin_id, data)
    return PluginResponse.model_validate(plugin)


@router.delete(
    "/{plugin_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_plugin_endpoint(
    plugin_id: str,
    token_payload: dict[str, Any] = Depends(  # noqa: B008
        _admin_dep
    ),
    session: AsyncIterator[AsyncSession] = Depends(  # noqa: B008
        get_db_session
    ),
) -> None:
    """delete a plugin (admin only)."""
    db: AsyncSession = session  # type: ignore[assignment]
    deleted = await delete_plugin(db, plugin_id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="plugin not found",
        )


# --- webhook endpoints ---


@router.post(
    "/{plugin_id}/webhooks",
    response_model=WebhookResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_webhook_endpoint(
    plugin_id: str,
    body: WebhookCreate,
    token_payload: dict[str, Any] = Depends(  # noqa: B008
        _admin_dep
    ),
    session: AsyncIterator[AsyncSession] = Depends(  # noqa: B008
        get_db_session
    ),
) -> WebhookResponse:
    """create a webhook for a plugin (admin only)."""
    db: AsyncSession = session  # type: ignore[assignment]
    # verify plugin exists
    plugin = await get_plugin(db, plugin_id)
    if not plugin:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="plugin not found",
        )
    data = body.model_dump()
    data["plugin_id"] = plugin.id
    webhook = await create_webhook(db, data)
    return WebhookResponse.model_validate(webhook)


@router.get(
    "/{plugin_id}/webhooks",
    response_model=WebhookListResponse,
)
async def list_webhooks_endpoint(
    plugin_id: str,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    token_payload: dict[str, Any] = Depends(  # noqa: B008
        require_authenticated
    ),
    session: AsyncIterator[AsyncSession] = Depends(  # noqa: B008
        get_db_session
    ),
) -> WebhookListResponse:
    """list webhooks for a plugin."""
    db: AsyncSession = session  # type: ignore[assignment]
    webhooks, total = await list_webhooks(db, plugin_id, skip, limit)
    items = [WebhookResponse.model_validate(w) for w in webhooks]
    return WebhookListResponse(items=items, total=total)


@router.patch(
    "/{plugin_id}/webhooks/{webhook_id}",
    response_model=WebhookResponse,
)
async def update_webhook_endpoint(
    plugin_id: str,
    webhook_id: str,
    body: WebhookUpdate,
    token_payload: dict[str, Any] = Depends(  # noqa: B008
        _admin_dep
    ),
    session: AsyncIterator[AsyncSession] = Depends(  # noqa: B008
        get_db_session
    ),
) -> WebhookResponse:
    """update a webhook (admin only)."""
    db: AsyncSession = session  # type: ignore[assignment]
    existing = await get_webhook(db, webhook_id)
    if not existing or str(existing.plugin_id) != plugin_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="webhook not found",
        )
    data = body.model_dump(exclude_unset=True)
    webhook = await update_webhook(db, webhook_id, data)
    return WebhookResponse.model_validate(webhook)


@router.delete(
    "/{plugin_id}/webhooks/{webhook_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_webhook_endpoint(
    plugin_id: str,
    webhook_id: str,
    token_payload: dict[str, Any] = Depends(  # noqa: B008
        _admin_dep
    ),
    session: AsyncIterator[AsyncSession] = Depends(  # noqa: B008
        get_db_session
    ),
) -> None:
    """delete a webhook (admin only)."""
    db: AsyncSession = session  # type: ignore[assignment]
    existing = await get_webhook(db, webhook_id)
    if not existing or str(existing.plugin_id) != plugin_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="webhook not found",
        )
    deleted = await delete_webhook(db, webhook_id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="webhook not found",
        )


@router.get(
    "/{plugin_id}/webhooks/{webhook_id}/deliveries",
    response_model=WebhookDeliveryListResponse,
)
async def list_deliveries_endpoint(
    plugin_id: str,
    webhook_id: str,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    token_payload: dict[str, Any] = Depends(  # noqa: B008
        require_authenticated
    ),
    session: AsyncIterator[AsyncSession] = Depends(  # noqa: B008
        get_db_session
    ),
) -> WebhookDeliveryListResponse:
    """get delivery log for a webhook."""
    db: AsyncSession = session  # type: ignore[assignment]
    existing = await get_webhook(db, webhook_id)
    if not existing or str(existing.plugin_id) != plugin_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="webhook not found",
        )
    deliveries, total = await get_deliveries(db, webhook_id, skip, limit)
    items = [WebhookDeliveryResponse.model_validate(d) for d in deliveries]
    return WebhookDeliveryListResponse(items=items, total=total)
