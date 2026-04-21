"""unit tests for loom.services.plugin."""

from unittest.mock import AsyncMock, MagicMock
from uuid import UUID, uuid4

import pytest

from loom.models.plugin import Plugin
from loom.services.plugin import (
    create_plugin,
    delete_plugin,
    disable_plugin,
    enable_plugin,
    get_plugin,
    list_plugins,
    update_plugin,
)

_USER_ID = str(uuid4())
_PLUGIN_ID = str(uuid4())


def _mock_session() -> AsyncMock:
    s = AsyncMock()
    s.add = MagicMock()
    s.commit = AsyncMock()
    s.refresh = AsyncMock()
    s.delete = AsyncMock()
    return s


# ── create_plugin ───────────────────────────────────────────


class TestCreatePlugin:
    @pytest.mark.asyncio
    async def test_creates_plugin_with_all_fields(self) -> None:
        """stores all fields from data dict."""
        session = _mock_session()
        data = {
            "name": "transcription-worker",
            "description": "Auto-transcription plugin",
            "version": "2.1.0",
            "plugin_type": "worker",
            "config": {"model": "whisper-large"},
        }
        result = await create_plugin(session, data, _USER_ID)
        assert isinstance(result, Plugin)
        assert result.name == "transcription-worker"
        assert result.description == "Auto-transcription plugin"
        assert result.version == "2.1.0"
        assert result.plugin_type == "worker"
        assert result.config == {"model": "whisper-large"}
        assert result.created_by == UUID(_USER_ID)
        session.add.assert_called_once()
        session.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_optional_fields_default_none(self) -> None:
        """description and config default to none."""
        session = _mock_session()
        data = {
            "name": "simple",
            "version": "1.0.0",
            "plugin_type": "webhook",
        }
        result = await create_plugin(session, data, _USER_ID)
        assert result.description is None
        assert result.config is None


# ── get_plugin ──────────────────────────────────────────────


class TestGetPlugin:
    @pytest.mark.asyncio
    async def test_returns_plugin(self) -> None:
        session = _mock_session()
        plugin = Plugin(
            name="p",
            version="1.0",
            plugin_type="webhook",
            created_by=UUID(_USER_ID),
        )
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = plugin
        session.execute.return_value = mock_result

        assert await get_plugin(session, _PLUGIN_ID) is plugin

    @pytest.mark.asyncio
    async def test_returns_none(self) -> None:
        session = _mock_session()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        session.execute.return_value = mock_result

        assert await get_plugin(session, _PLUGIN_ID) is None


# ── list_plugins ────────────────────────────────────────────


class TestListPlugins:
    @pytest.mark.asyncio
    async def test_returns_paginated_plugins(self) -> None:
        """returns plugins and total count."""
        session = _mock_session()
        plugin = Plugin(
            name="p",
            version="1.0",
            plugin_type="webhook",
            created_by=UUID(_USER_ID),
        )
        count_result = MagicMock()
        count_result.scalar_one.return_value = 1
        data_result = MagicMock()
        data_scalars = MagicMock()
        data_scalars.all.return_value = [plugin]
        data_result.scalars.return_value = data_scalars
        session.execute.side_effect = [count_result, data_result]

        plugins, total = await list_plugins(session)
        assert total == 1
        assert len(plugins) == 1

    @pytest.mark.asyncio
    async def test_empty_result(self) -> None:
        session = _mock_session()
        count_result = MagicMock()
        count_result.scalar_one.return_value = 0
        data_result = MagicMock()
        data_scalars = MagicMock()
        data_scalars.all.return_value = []
        data_result.scalars.return_value = data_scalars
        session.execute.side_effect = [count_result, data_result]

        plugins, total = await list_plugins(session)
        assert total == 0
        assert plugins == []

    @pytest.mark.asyncio
    async def test_type_filter_accepted(self) -> None:
        """plugin_type filter does not raise."""
        session = _mock_session()
        count_result = MagicMock()
        count_result.scalar_one.return_value = 0
        data_result = MagicMock()
        data_scalars = MagicMock()
        data_scalars.all.return_value = []
        data_result.scalars.return_value = data_scalars
        session.execute.side_effect = [count_result, data_result]

        await list_plugins(session, plugin_type="worker")


# ── update_plugin ───────────────────────────────────────────


class TestUpdatePlugin:
    @pytest.mark.asyncio
    async def test_partial_update(self) -> None:
        """updates only non-none fields."""
        session = _mock_session()
        plugin = Plugin(
            name="p",
            version="1.0",
            description="old",
            plugin_type="webhook",
            created_by=UUID(_USER_ID),
        )
        mock_result = MagicMock()
        mock_result.scalar_one.return_value = plugin
        session.execute.return_value = mock_result

        updated = await update_plugin(
            session,
            _PLUGIN_ID,
            {"version": "2.0", "description": None},
        )
        assert updated.version == "2.0"
        # description stays because none is skipped
        assert updated.description == "old"
        session.commit.assert_awaited_once()
        session.refresh.assert_awaited_once_with(plugin)


# ── delete_plugin ───────────────────────────────────────────


class TestDeletePlugin:
    @pytest.mark.asyncio
    async def test_deletes_existing(self) -> None:
        session = _mock_session()
        plugin = Plugin(
            name="p",
            version="1.0",
            plugin_type="webhook",
            created_by=UUID(_USER_ID),
        )
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = plugin
        session.execute.return_value = mock_result

        assert await delete_plugin(session, _PLUGIN_ID) is True
        session.delete.assert_awaited_once_with(plugin)
        session.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_returns_false_when_missing(self) -> None:
        session = _mock_session()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        session.execute.return_value = mock_result

        assert await delete_plugin(session, _PLUGIN_ID) is False
        session.delete.assert_not_awaited()


# ── enable_plugin / disable_plugin ──────────────────────────


class TestEnableDisable:
    @pytest.mark.asyncio
    async def test_enable_sets_is_enabled_true(self) -> None:
        """enable_plugin delegates to update with is_enabled=True."""
        session = _mock_session()
        plugin = Plugin(
            name="p",
            version="1.0",
            plugin_type="webhook",
            is_enabled=False,
            created_by=UUID(_USER_ID),
        )
        mock_result = MagicMock()
        mock_result.scalar_one.return_value = plugin
        session.execute.return_value = mock_result

        result = await enable_plugin(session, _PLUGIN_ID)
        assert result.is_enabled is True

    @pytest.mark.asyncio
    async def test_disable_sets_is_enabled_false(self) -> None:
        """disable_plugin delegates to update with is_enabled=False."""
        session = _mock_session()
        plugin = Plugin(
            name="p",
            version="1.0",
            plugin_type="webhook",
            is_enabled=True,
            created_by=UUID(_USER_ID),
        )
        mock_result = MagicMock()
        mock_result.scalar_one.return_value = plugin
        session.execute.return_value = mock_result

        result = await disable_plugin(session, _PLUGIN_ID)
        # is_enabled=False is not None, so it gets set
        assert result.is_enabled is False
