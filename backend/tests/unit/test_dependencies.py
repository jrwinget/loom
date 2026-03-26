"""unit tests for dependency injection functions."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from loom.dependencies import get_db_session, get_minio_client, get_settings


@pytest.mark.asyncio
async def test_get_db_session_yields_session() -> None:
    """get_db_session yields session from app state factory."""
    mock_session = AsyncMock()
    mock_factory = MagicMock()

    # factory returns an async context manager
    mock_cm = AsyncMock()
    mock_cm.__aenter__ = AsyncMock(return_value=mock_session)
    mock_cm.__aexit__ = AsyncMock(return_value=False)
    mock_factory.return_value = mock_cm

    mock_request = MagicMock()
    mock_request.app.state.db_session_factory = mock_factory

    gen = get_db_session(mock_request)
    session = await gen.__anext__()
    assert session is mock_session


def test_get_minio_client_returns_client() -> None:
    """get_minio_client returns client from app state."""
    mock_client = MagicMock()
    mock_request = MagicMock()
    mock_request.app.state.minio_client = mock_client

    result = get_minio_client(mock_request)
    assert result is mock_client


def test_get_settings_returns_instance() -> None:
    """get_settings returns a Settings instance."""
    with patch(
        "loom.dependencies._get_settings",
    ) as mock_gs:
        mock_settings = MagicMock()
        mock_gs.return_value = mock_settings

        result = get_settings()
        assert result is mock_settings
        mock_gs.assert_called_once()
