from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from loom.models.plugin import Plugin


async def create_plugin(
    session: AsyncSession,
    data: dict[str, Any],
    user_id: str,
) -> Plugin:
    """register a new plugin."""
    plugin = Plugin(
        name=data["name"],
        description=data.get("description"),
        version=data["version"],
        plugin_type=data["plugin_type"],
        config=data.get("config"),
        created_by=UUID(user_id),
    )
    session.add(plugin)
    await session.commit()
    await session.refresh(plugin)
    return plugin


async def list_plugins(
    session: AsyncSession,
    plugin_type: str | None = None,
    skip: int = 0,
    limit: int = 50,
) -> tuple[list[Plugin], int]:
    """list plugins with optional type filter."""
    query = select(Plugin)
    if plugin_type is not None:
        query = query.where(Plugin.plugin_type == plugin_type)

    # total count
    count_query = select(func.count()).select_from(
        query.with_only_columns(Plugin.id).subquery()
    )
    total_result = await session.execute(count_query)
    total = total_result.scalar_one()

    # paginated results
    query = query.order_by(Plugin.created_at.desc())
    query = query.offset(skip).limit(limit)
    result = await session.execute(query)
    plugins = list(result.scalars().all())

    return plugins, total


async def get_plugin(
    session: AsyncSession,
    plugin_id: str,
) -> Plugin | None:
    """get a single plugin by id."""
    result = await session.execute(
        select(Plugin).where(Plugin.id == UUID(plugin_id))
    )
    return result.scalar_one_or_none()


async def update_plugin(
    session: AsyncSession,
    plugin_id: str,
    data: dict[str, Any],
) -> Plugin:
    """update plugin fields."""
    result = await session.execute(
        select(Plugin).where(Plugin.id == UUID(plugin_id))
    )
    plugin = result.scalar_one()

    for key, value in data.items():
        if value is not None:
            setattr(plugin, key, value)

    await session.commit()
    await session.refresh(plugin)
    return plugin


async def delete_plugin(
    session: AsyncSession,
    plugin_id: str,
) -> bool:
    """delete a plugin and its webhooks."""
    result = await session.execute(
        select(Plugin).where(Plugin.id == UUID(plugin_id))
    )
    plugin = result.scalar_one_or_none()
    if not plugin:
        return False

    await session.delete(plugin)
    await session.commit()
    return True


async def enable_plugin(
    session: AsyncSession,
    plugin_id: str,
) -> Plugin:
    """enable a plugin."""
    return await update_plugin(session, plugin_id, {"is_enabled": True})


async def disable_plugin(
    session: AsyncSession,
    plugin_id: str,
) -> Plugin:
    """disable a plugin."""
    return await update_plugin(session, plugin_id, {"is_enabled": False})
