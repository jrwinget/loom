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


class TestCreateWebhook:
    """create_webhook persists a webhook."""

    @pytest.mark.asyncio
    async def test_creates_webhook(self) -> None:
        """creates and returns webhook."""
        from loom.services.webhook import create_webhook

        session = AsyncMock()
        data = {
            "plugin_id": _PLUGIN_ID,
            "url": "https://example.com/hook",
            "events": ["asset.uploaded"],
            "secret": "s3cret",
        }

        await create_webhook(session, data)
        session.add.assert_called_once()
        session.commit.assert_awaited_once()
        session.refresh.assert_awaited_once()


class TestListWebhooks:
    """list_webhooks with optional plugin filter."""

    @pytest.mark.asyncio
    async def test_returns_webhooks_and_total(self) -> None:
        """returns list and total count."""
        from loom.services.webhook import list_webhooks

        webhook = MagicMock(spec=Webhook)
        webhook.id = _WEBHOOK_ID

        session = AsyncMock()
        call_count = 0

        async def mock_execute(query: object) -> MagicMock:
            nonlocal call_count
            call_count += 1
            m = MagicMock()
            if call_count == 1:
                m.scalar_one.return_value = 1
            else:
                m.scalars.return_value.all.return_value = [webhook]
            return m

        session.execute = AsyncMock(side_effect=mock_execute)

        webhooks, total = await list_webhooks(session)
        assert total == 1
        assert len(webhooks) == 1

    @pytest.mark.asyncio
    async def test_filter_by_plugin(self) -> None:
        """filters by plugin_id."""
        from loom.services.webhook import list_webhooks

        session = AsyncMock()
        call_count = 0

        async def mock_execute(query: object) -> MagicMock:
            nonlocal call_count
            call_count += 1
            m = MagicMock()
            if call_count == 1:
                m.scalar_one.return_value = 0
            else:
                m.scalars.return_value.all.return_value = []
            return m

        session.execute = AsyncMock(side_effect=mock_execute)

        webhooks, total = await list_webhooks(
            session, plugin_id=str(_PLUGIN_ID)
        )
        assert total == 0
        assert webhooks == []


class TestUpdateWebhook:
    """update_webhook modifies fields."""

    @pytest.mark.asyncio
    async def test_updates_fields(self) -> None:
        """updates specified fields."""
        from loom.services.webhook import update_webhook

        webhook = MagicMock(spec=Webhook)
        webhook.id = _WEBHOOK_ID
        webhook.url = "https://old.com/hook"

        session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one.return_value = webhook
        session.execute = AsyncMock(return_value=mock_result)

        await update_webhook(
            session,
            str(_WEBHOOK_ID),
            {"url": "https://new.com/hook"},
        )

        session.commit.assert_awaited_once()
        session.refresh.assert_awaited_once()


class TestDeleteWebhook:
    """delete_webhook removes a webhook."""

    @pytest.mark.asyncio
    async def test_deletes_existing(self) -> None:
        """returns True when deleted."""
        from loom.services.webhook import delete_webhook

        webhook = MagicMock(spec=Webhook)

        session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = webhook
        session.execute = AsyncMock(return_value=mock_result)

        result = await delete_webhook(session, str(_WEBHOOK_ID))
        assert result is True
        session.delete.assert_awaited_once()
        session.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_returns_false_for_missing(self) -> None:
        """returns False when not found."""
        from loom.services.webhook import delete_webhook

        session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        session.execute = AsyncMock(return_value=mock_result)

        result = await delete_webhook(session, str(_WEBHOOK_ID))
        assert result is False


class TestDispatchMultiple:
    """dispatch_event with multiple matching webhooks."""

    @pytest.mark.asyncio
    async def test_dispatches_to_multiple(self) -> None:
        """dispatches to all matching webhooks."""
        w1 = MagicMock(spec=Webhook)
        w1.id = _WEBHOOK_ID
        w1.url = "https://one.com/hook"
        w1.events = ["asset.uploaded"]
        w1.is_active = True
        w1.failure_count = 0
        w1.secret = None
        w1.last_triggered_at = None

        w2 = MagicMock(spec=Webhook)
        w2.id = UUID("01912345-6789-7abc-8def-0123456789ff")
        w2.url = "https://two.com/hook"
        w2.events = ["asset.uploaded"]
        w2.is_active = True
        w2.failure_count = 0
        w2.secret = None
        w2.last_triggered_at = None

        session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [w1, w2]
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

            assert mock_client.post.call_count == 2

    @pytest.mark.asyncio
    async def test_no_matching_webhooks_noop(self) -> None:
        """no matching webhooks results in no-op."""
        session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        session.execute = AsyncMock(return_value=mock_result)

        # should not raise
        await dispatch_event(
            session,
            "unknown.event",
            {"data": "test"},
        )


class TestGetDeliveries:
    """get_deliveries pagination."""

    @pytest.mark.asyncio
    async def test_returns_deliveries_and_total(self) -> None:
        """returns paginated deliveries."""
        from loom.services.webhook import get_deliveries

        delivery = MagicMock()
        delivery.id = UUID("01912345-6789-7abc-8def-012345678900")

        session = AsyncMock()
        call_count = 0

        async def mock_execute(query: object) -> MagicMock:
            nonlocal call_count
            call_count += 1
            m = MagicMock()
            if call_count == 1:
                m.scalar_one.return_value = 1
            else:
                m.scalars.return_value.all.return_value = [delivery]
            return m

        session.execute = AsyncMock(side_effect=mock_execute)

        deliveries, total = await get_deliveries(session, str(_WEBHOOK_ID))
        assert total == 1
        assert len(deliveries) == 1

    @pytest.mark.asyncio
    async def test_empty_deliveries(self) -> None:
        """returns empty list when no deliveries."""
        from loom.services.webhook import get_deliveries

        session = AsyncMock()
        call_count = 0

        async def mock_execute(query: object) -> MagicMock:
            nonlocal call_count
            call_count += 1
            m = MagicMock()
            if call_count == 1:
                m.scalar_one.return_value = 0
            else:
                m.scalars.return_value.all.return_value = []
            return m

        session.execute = AsyncMock(side_effect=mock_execute)

        deliveries, total = await get_deliveries(session, str(_WEBHOOK_ID))
        assert total == 0
        assert deliveries == []


class TestDeliveryRecording:
    """delivery recording on success and failure."""

    @pytest.mark.asyncio
    async def test_records_successful_delivery(self) -> None:
        """successful delivery records status_code and response."""
        webhook = MagicMock(spec=Webhook)
        webhook.id = _WEBHOOK_ID
        webhook.url = "https://example.com/hook"
        webhook.events = ["test.event"]
        webhook.is_active = True
        webhook.failure_count = 3
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
                "test.event",
                {"data": "value"},
            )

        # delivery was recorded
        session.add.assert_called_once()
        added = session.add.call_args[0][0]
        assert added.status_code == 200
        assert webhook.failure_count == 0

    @pytest.mark.asyncio
    async def test_records_failed_delivery(self) -> None:
        """http error increments failure_count."""
        webhook = MagicMock(spec=Webhook)
        webhook.id = _WEBHOOK_ID
        webhook.url = "https://example.com/hook"
        webhook.events = ["test.event"]
        webhook.is_active = True
        webhook.failure_count = 0
        webhook.secret = None
        webhook.last_triggered_at = None

        session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [webhook]
        session.execute = AsyncMock(return_value=mock_result)

        mock_response = MagicMock(spec=httpx.Response)
        mock_response.status_code = 500
        mock_response.is_success = False
        mock_response.text = "error"

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
                "test.event",
                {"data": "value"},
            )

        assert webhook.failure_count == 1
