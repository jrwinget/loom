"""tests for SSRF protection in webhook URL validation."""

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID

import httpx
import pytest
from pydantic import ValidationError

from loom.models.plugin import Webhook
from loom.schemas.plugin import WebhookCreate

_WEBHOOK_ID = UUID("01912345-6789-7abc-8def-0123456789ab")
_PLUGIN_ID = UUID("01912345-6789-7abc-8def-0123456789cd")


def _fake_getaddrinfo(
    ip: str,
) -> list[tuple[int, int, int, str, tuple[str, int]]]:
    """build a fake socket.getaddrinfo return value."""
    import socket

    return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (ip, 443))]


class TestWebhookUrlValidation:
    """schema-level SSRF prevention on WebhookCreate."""

    def test_rejects_private_ipv4_10(self) -> None:
        """rejects urls resolving to 10.0.0.0/8."""
        with (
            patch(
                "loom.schemas.plugin.socket.getaddrinfo",
                return_value=_fake_getaddrinfo("10.0.0.1"),
            ),
            pytest.raises(ValidationError, match="private"),
        ):
            WebhookCreate(
                plugin_id=_PLUGIN_ID,
                url="https://internal.example.com/hook",
                events=["asset.uploaded"],
            )

    def test_rejects_loopback(self) -> None:
        """rejects urls resolving to 127.0.0.0/8."""
        with (
            patch(
                "loom.schemas.plugin.socket.getaddrinfo",
                return_value=_fake_getaddrinfo("127.0.0.1"),
            ),
            pytest.raises(ValidationError, match="private"),
        ):
            WebhookCreate(
                plugin_id=_PLUGIN_ID,
                url="https://localhost/hook",
                events=["asset.uploaded"],
            )

    def test_rejects_link_local(self) -> None:
        """rejects urls resolving to 169.254.0.0/16."""
        with (
            patch(
                "loom.schemas.plugin.socket.getaddrinfo",
                return_value=_fake_getaddrinfo("169.254.1.1"),
            ),
            pytest.raises(ValidationError, match="private"),
        ):
            WebhookCreate(
                plugin_id=_PLUGIN_ID,
                url="https://link-local.example.com/hook",
                events=["asset.uploaded"],
            )

    def test_rejects_ipv6_loopback(self) -> None:
        """rejects urls resolving to ::1."""
        import socket

        with (
            patch(
                "loom.schemas.plugin.socket.getaddrinfo",
                return_value=[
                    (
                        socket.AF_INET6,
                        socket.SOCK_STREAM,
                        6,
                        "",
                        ("::1", 443, 0, 0),
                    )
                ],
            ),
            pytest.raises(ValidationError, match="private"),
        ):
            WebhookCreate(
                plugin_id=_PLUGIN_ID,
                url="https://[::1]/hook",
                events=["asset.uploaded"],
            )

    def test_rejects_ftp_scheme(self) -> None:
        """rejects non-http(s) schemes like ftp."""
        with pytest.raises(ValidationError, match="http or https"):
            WebhookCreate(
                plugin_id=_PLUGIN_ID,
                url="ftp://example.com/hook",
                events=["asset.uploaded"],
            )

    def test_rejects_file_scheme(self) -> None:
        """rejects file:// scheme."""
        with pytest.raises(ValidationError, match="http or https"):
            WebhookCreate(
                plugin_id=_PLUGIN_ID,
                url="file:///etc/passwd",
                events=["asset.uploaded"],
            )

    def test_allows_public_https(self) -> None:
        """allows urls resolving to public IPs over https."""
        with patch(
            "loom.schemas.plugin.socket.getaddrinfo",
            return_value=_fake_getaddrinfo("93.184.216.34"),
        ):
            wh = WebhookCreate(
                plugin_id=_PLUGIN_ID,
                url="https://example.com/hook",
                events=["asset.uploaded"],
            )
            assert wh.url == "https://example.com/hook"

    def test_allows_public_http(self) -> None:
        """allows urls resolving to public IPs over http."""
        with patch(
            "loom.schemas.plugin.socket.getaddrinfo",
            return_value=_fake_getaddrinfo("93.184.216.34"),
        ):
            wh = WebhookCreate(
                plugin_id=_PLUGIN_ID,
                url="http://example.com/hook",
                events=["asset.uploaded"],
            )
            assert wh.url == "http://example.com/hook"


class TestSsrfDeliveryProtection:
    """runtime SSRF protection in webhook delivery."""

    @pytest.mark.asyncio
    async def test_skips_delivery_for_private_ip(self) -> None:
        """delivery is skipped when url resolves to private IP."""
        from loom.services.webhook import dispatch_event

        webhook = MagicMock(spec=Webhook)
        webhook.id = _WEBHOOK_ID
        webhook.plugin_id = _PLUGIN_ID
        webhook.url = "https://evil.example.com/hook"
        webhook.events = ["asset.uploaded"]
        webhook.is_active = True
        webhook.failure_count = 0
        webhook.secret = None
        webhook.last_triggered_at = None

        session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [webhook]
        session.execute = AsyncMock(return_value=mock_result)

        with (
            patch("loom.services.webhook.httpx.AsyncClient") as mock_client_cls,
            patch(
                "loom.services.webhook.socket.getaddrinfo",
                return_value=_fake_getaddrinfo("10.0.0.1"),
            ),
        ):
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

            # post should NOT be called due to SSRF block
            mock_client.post.assert_not_called()

    @pytest.mark.asyncio
    async def test_delivers_for_public_ip(self) -> None:
        """delivery proceeds when url resolves to public IP."""
        from loom.services.webhook import dispatch_event

        webhook = MagicMock(spec=Webhook)
        webhook.id = _WEBHOOK_ID
        webhook.plugin_id = _PLUGIN_ID
        webhook.url = "https://example.com/hook"
        webhook.events = ["asset.uploaded"]
        webhook.is_active = True
        webhook.failure_count = 0
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

        with (
            patch("loom.services.webhook.httpx.AsyncClient") as mock_client_cls,
            patch(
                "loom.services.webhook.socket.getaddrinfo",
                return_value=_fake_getaddrinfo("93.184.216.34"),
            ),
        ):
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

            # post should be called for public IP
            mock_client.post.assert_called_once()
