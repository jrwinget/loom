"""tests for the shared workflow infrastructure module."""

from unittest.mock import MagicMock, patch

import pytest

from loom.workflows.shared import (
    get_db_session,
    get_minio_client,
    reset_for_testing,
)


@pytest.fixture(autouse=True)
def _reset_shared() -> None:
    """reset module caches before each test."""
    reset_for_testing()


class TestGetMinioClient:
    """get_minio_client returns a cached minio client."""

    @patch("loom.workflows.shared.get_settings")
    @patch("loom.workflows.shared.Minio")
    def test_creates_client_on_first_call(
        self,
        mock_minio_cls: MagicMock,
        mock_settings: MagicMock,
    ) -> None:
        """creates minio client using settings."""
        settings = MagicMock()
        settings.minio_endpoint = "localhost:9000"
        settings.minio_access_key = "key"
        settings.minio_secret_key = "secret"
        settings.minio_secure = False
        mock_settings.return_value = settings

        client = get_minio_client()

        mock_minio_cls.assert_called_once_with(
            "localhost:9000",
            access_key="key",
            secret_key="secret",
            secure=False,
        )
        assert client == mock_minio_cls.return_value

    @patch("loom.workflows.shared.get_settings")
    @patch("loom.workflows.shared.Minio")
    def test_returns_cached_on_second_call(
        self,
        mock_minio_cls: MagicMock,
        mock_settings: MagicMock,
    ) -> None:
        """returns same client on subsequent calls."""
        settings = MagicMock()
        mock_settings.return_value = settings

        first = get_minio_client()
        second = get_minio_client()

        assert first is second
        assert mock_minio_cls.call_count == 1


class TestResetForTesting:
    """reset_for_testing clears cached state."""

    @patch("loom.workflows.shared.get_settings")
    @patch("loom.workflows.shared.Minio")
    def test_reset_clears_minio_cache(
        self,
        mock_minio_cls: MagicMock,
        mock_settings: MagicMock,
    ) -> None:
        """after reset, next call creates a new client."""
        settings = MagicMock()
        mock_settings.return_value = settings

        # return distinct objects per call
        mock_minio_cls.side_effect = [
            MagicMock(name="first"),
            MagicMock(name="second"),
        ]

        first = get_minio_client()
        reset_for_testing()
        second = get_minio_client()

        assert first is not second
        assert mock_minio_cls.call_count == 2


class TestGetDbSession:
    """get_db_session returns an async context manager."""

    @patch("loom.workflows.shared.get_settings")
    @patch("loom.workflows.shared.create_async_engine")
    async def test_session_is_async_context_manager(
        self,
        mock_engine: MagicMock,
        mock_settings: MagicMock,
    ) -> None:
        """session factory produces a usable context manager."""
        # verify get_db_session is an async context manager
        ctx = get_db_session()
        assert hasattr(ctx, "__aenter__")
        assert hasattr(ctx, "__aexit__")
