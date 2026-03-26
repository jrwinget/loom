import hashlib
import hmac
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID

import httpx
import pytest

from loom.models.plugin import Plugin, Webhook
from loom.services.webhook import compute_signature, dispatch_event

_WEBHOOK_ID = UUID("01912345-6789-7abc-8def-0123456789ab")
_PLUGIN_ID = UUID("01912345-6789-7abc-8def-0123456789cd")


class TestHmacSignature:
    """hmac signature computation."""

    def test_compute_signature(self) -> None:
        """signature matches expected hmac-sha256."""
        secret = "my-secret"  # noqa: S105
        payload = '{"event": "test"}'
        expected = hmac.new(
            secret.encode(),
            payload.encode(),
            hashlib.sha256,
        ).hexdigest()
        assert compute_signature(secret, payload) == expected

    def test_different_secrets_differ(self) -> None:
        """different secrets produce different signatures."""
        payload = '{"event": "test"}'
        sig1 = compute_signature("secret-a", payload)
        sig2 = compute_signature("secret-b", payload)
        assert sig1 != sig2

    def test_different_payloads_differ(self) -> None:
        """different payloads produce different signatures."""
        secret = "same-secret"  # noqa: S105
        sig1 = compute_signature(secret, '{"a": 1}')
        sig2 = compute_signature(secret, '{"b": 2}')
        assert sig1 != sig2


class TestEventMatching:
    """event type matching for webhook dispatch."""

    def _make_webhook(
        self,
        events: list[str],
        *,
        is_active: bool = True,
        failure_count: int = 0,
        secret: str | None = None,
    ) -> MagicMock:
        """build a mock webhook."""
        w = MagicMock(spec=Webhook)
        w.id = _WEBHOOK_ID
        w.plugin_id = _PLUGIN_ID
        w.url = "https://example.com/hook"
        w.events = events
        w.is_active = is_active
        w.failure_count = failure_count
        w.secret = secret
        w.last_triggered_at = None
        return w

    def _make_plugin(self, *, is_enabled: bool = True) -> MagicMock:
        """build a mock plugin."""
        p = MagicMock(spec=Plugin)
        p.id = _PLUGIN_ID
        p.is_enabled = is_enabled
        return p

    @pytest.mark.asyncio
    async def test_matching_event_dispatched(self) -> None:
        """webhook subscribed to event gets called."""
        webhook = self._make_webhook(["asset.uploaded"], secret="s3cret")

        session = AsyncMock()
        # return webhook from query
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [webhook]
        session.execute = AsyncMock(return_value=mock_result)

        mock_response = MagicMock(spec=httpx.Response)
        mock_response.status_code = 200
        mock_response.is_success = True
        mock_response.text = "ok"

        with patch(
            "loom.services.webhook.httpx.AsyncClient"
        ) as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client_cls.return_value.__aenter__ = AsyncMock(
                return_value=mock_client
            )
            mock_client_cls.return_value.__aexit__ = AsyncMock(
                return_value=False
            )

            await dispatch_event(
                session,
                "asset.uploaded",
                {"asset_id": "123"},
            )

            mock_client.post.assert_called_once()

    @pytest.mark.asyncio
    async def test_non_matching_event_skipped(self) -> None:
        """webhook not subscribed to event is not called."""
        webhook = self._make_webhook(["case.created"])

        session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [webhook]
        session.execute = AsyncMock(return_value=mock_result)

        with patch(
            "loom.services.webhook.httpx.AsyncClient"
        ) as mock_client_cls:
            mock_client = AsyncMock()
            mock_client_cls.return_value.__aenter__ = AsyncMock(
                return_value=mock_client
            )
            mock_client_cls.return_value.__aexit__ = AsyncMock(
                return_value=False
            )

            await dispatch_event(
                session,
                "asset.uploaded",
                {"asset_id": "123"},
            )

            mock_client.post.assert_not_called()


class TestAutoDisable:
    """auto-disable after consecutive failures."""

    @pytest.mark.asyncio
    async def test_auto_disable_after_10_failures(
        self,
    ) -> None:
        """webhook is disabled after 10 failures."""
        webhook = MagicMock(spec=Webhook)
        webhook.id = _WEBHOOK_ID
        webhook.plugin_id = _PLUGIN_ID
        webhook.url = "https://example.com/hook"
        webhook.events = ["asset.uploaded"]
        webhook.is_active = True
        webhook.failure_count = 9
        webhook.secret = None
        webhook.last_triggered_at = None

        session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [webhook]
        session.execute = AsyncMock(return_value=mock_result)

        # simulate http failure
        with patch(
            "loom.services.webhook.httpx.AsyncClient"
        ) as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(side_effect=httpx.ConnectError("fail"))
            mock_client_cls.return_value.__aenter__ = AsyncMock(
                return_value=mock_client
            )
            mock_client_cls.return_value.__aexit__ = AsyncMock(
                return_value=False
            )

            await dispatch_event(
                session,
                "asset.uploaded",
                {"asset_id": "123"},
            )

        # failure_count should be 10, webhook auto-disabled
        assert webhook.failure_count >= 10
        assert webhook.is_active is False

    @pytest.mark.asyncio
    async def test_success_resets_failure_count(
        self,
    ) -> None:
        """successful delivery resets failure count."""
        webhook = MagicMock(spec=Webhook)
        webhook.id = _WEBHOOK_ID
        webhook.plugin_id = _PLUGIN_ID
        webhook.url = "https://example.com/hook"
        webhook.events = ["asset.uploaded"]
        webhook.is_active = True
        webhook.failure_count = 5
        webhook.secret = None
        webhook.last_triggered_at = None

        session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [webhook]
        session.execute = AsyncMock(return_value=mock_result)

        mock_response = MagicMock(spec=httpx.Response)
        mock_response.status_code = 200
        mock_response.is_success = True
        mock_response.text = "ok"

        with patch(
            "loom.services.webhook.httpx.AsyncClient"
        ) as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client_cls.return_value.__aenter__ = AsyncMock(
                return_value=mock_client
            )
            mock_client_cls.return_value.__aexit__ = AsyncMock(
                return_value=False
            )

            await dispatch_event(
                session,
                "asset.uploaded",
                {"asset_id": "123"},
            )

        assert webhook.failure_count == 0
