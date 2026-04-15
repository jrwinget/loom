import hashlib
import hmac
import ipaddress
import json
import logging
import socket
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlparse
from uuid import UUID

import httpx
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from loom.models.plugin import Plugin, Webhook, WebhookDelivery

logger = logging.getLogger(__name__)

# auto-disable after this many consecutive failures
_MAX_FAILURES = 10

_BLOCKED_NETWORKS = [
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("169.254.0.0/16"),
    ipaddress.ip_network("::1/128"),
    ipaddress.ip_network("fc00::/7"),
    ipaddress.ip_network("fe80::/10"),
]


def _validate_url_at_delivery(url: str) -> None:
    """validate webhook url does not resolve to private IP.

    raises ValueError if the url resolves to a blocked network.
    this catches DNS rebinding attacks where a hostname resolves
    to a public IP at registration but a private IP at delivery.
    """
    parsed = urlparse(url)
    hostname = parsed.hostname
    if not hostname:
        raise ValueError("webhook url has no hostname")
    addr_infos = socket.getaddrinfo(hostname, parsed.port or 443)
    for info in addr_infos:
        addr = ipaddress.ip_address(info[4][0])
        for network in _BLOCKED_NETWORKS:
            if addr in network:
                raise ValueError(
                    f"webhook url resolves to private/reserved address {addr}"
                )


def compute_signature(secret: str, payload_json: str) -> str:
    """compute hmac-sha256 signature for webhook payload."""
    return hmac.new(
        secret.encode(),
        payload_json.encode(),
        hashlib.sha256,
    ).hexdigest()


async def create_webhook(
    session: AsyncSession,
    data: dict[str, Any],
) -> Webhook:
    """create a new webhook subscription."""
    webhook = Webhook(
        plugin_id=data["plugin_id"],
        url=data["url"],
        events=data["events"],
        secret=data.get("secret"),
    )
    session.add(webhook)
    await session.commit()
    await session.refresh(webhook)
    return webhook


async def list_webhooks(
    session: AsyncSession,
    plugin_id: str | None = None,
    skip: int = 0,
    limit: int = 50,
) -> tuple[list[Webhook], int]:
    """list webhooks with optional plugin filter."""
    query = select(Webhook)
    if plugin_id is not None:
        query = query.where(Webhook.plugin_id == UUID(plugin_id))

    # total count
    count_query = select(func.count()).select_from(
        query.with_only_columns(Webhook.id).subquery()
    )
    total_result = await session.execute(count_query)
    total = total_result.scalar_one()

    # paginated results
    query = query.order_by(Webhook.created_at.desc())
    query = query.offset(skip).limit(limit)
    result = await session.execute(query)
    webhooks = list(result.scalars().all())

    return webhooks, total


async def get_webhook(
    session: AsyncSession,
    webhook_id: str,
) -> Webhook | None:
    """get a single webhook by id."""
    result = await session.execute(
        select(Webhook).where(Webhook.id == UUID(webhook_id))
    )
    return result.scalar_one_or_none()


async def update_webhook(
    session: AsyncSession,
    webhook_id: str,
    data: dict[str, Any],
) -> Webhook:
    """update webhook fields."""
    result = await session.execute(
        select(Webhook).where(Webhook.id == UUID(webhook_id))
    )
    webhook = result.scalar_one()

    for key, value in data.items():
        if value is not None:
            setattr(webhook, key, value)

    await session.commit()
    await session.refresh(webhook)
    return webhook


async def delete_webhook(
    session: AsyncSession,
    webhook_id: str,
) -> bool:
    """delete a webhook."""
    result = await session.execute(
        select(Webhook).where(Webhook.id == UUID(webhook_id))
    )
    webhook = result.scalar_one_or_none()
    if not webhook:
        return False

    await session.delete(webhook)
    await session.commit()
    return True


async def dispatch_event(
    session: AsyncSession,
    event_type: str,
    payload: dict[str, Any],
) -> None:
    """dispatch an event to all active subscribed webhooks.

    finds all active webhooks whose events list contains
    event_type, sends http post to each, and records
    delivery results. auto-disables after 10 consecutive
    failures.
    """
    # find active webhooks subscribed to this event type
    # whose parent plugin is also enabled
    query = (
        select(Webhook)
        .join(Plugin, Plugin.id == Webhook.plugin_id)
        .where(
            Webhook.is_active.is_(True),
            Plugin.is_enabled.is_(True),
        )
    )
    result = await session.execute(query)
    webhooks = list(result.scalars().all())

    # filter by event type (json array contains)
    matching = [w for w in webhooks if event_type in (w.events or [])]

    if not matching:
        return

    payload_json = json.dumps(payload, default=str)

    async with httpx.AsyncClient(timeout=10.0) as client:
        for webhook in matching:
            await _deliver(
                session,
                client,
                webhook,
                event_type,
                payload,
                payload_json,
            )


async def _deliver(
    session: AsyncSession,
    client: httpx.AsyncClient,
    webhook: Webhook,
    event_type: str,
    payload: dict[str, Any],
    payload_json: str,
) -> None:
    """send a single webhook delivery and record result."""
    headers: dict[str, str] = {
        "Content-Type": "application/json",
        "X-Loom-Event": event_type,
    }

    # add hmac signature if secret is configured
    if webhook.secret:
        sig = compute_signature(webhook.secret, payload_json)
        headers["X-Loom-Signature"] = sig

    delivery = WebhookDelivery(
        webhook_id=webhook.id,
        event_type=event_type,
        payload=payload,
    )

    # runtime SSRF check to catch DNS rebinding attacks
    try:
        _validate_url_at_delivery(webhook.url)
    except ValueError:
        logger.warning(
            "ssrf: skipping delivery to %s — resolves to "
            "private/reserved address",
            webhook.url,
        )
        return

    try:
        resp = await client.post(
            webhook.url,
            content=payload_json,
            headers=headers,
        )
        delivery.status_code = resp.status_code
        delivery.response_body = resp.text[:4096]
        delivery.delivered_at = datetime.now(UTC)

        if resp.is_success:
            # reset failure count on success
            webhook.failure_count = 0
        else:
            webhook.failure_count += 1
    except Exception:
        logger.warning(
            "webhook delivery failed for %s",
            webhook.url,
            exc_info=True,
        )
        webhook.failure_count += 1

    # auto-disable after too many consecutive failures
    if webhook.failure_count >= _MAX_FAILURES:
        webhook.is_active = False
        logger.warning(
            "auto-disabled webhook %s after %d failures",
            webhook.id,
            webhook.failure_count,
        )

    webhook.last_triggered_at = datetime.now(UTC)
    session.add(delivery)
    await session.commit()


async def get_deliveries(
    session: AsyncSession,
    webhook_id: str,
    skip: int = 0,
    limit: int = 50,
) -> tuple[list[WebhookDelivery], int]:
    """get delivery log for a webhook."""
    query = select(WebhookDelivery).where(
        WebhookDelivery.webhook_id == UUID(webhook_id)
    )

    # total count
    count_query = select(func.count()).select_from(
        query.with_only_columns(WebhookDelivery.id).subquery()
    )
    total_result = await session.execute(count_query)
    total = total_result.scalar_one()

    # paginated results
    query = query.order_by(WebhookDelivery.created_at.desc())
    query = query.offset(skip).limit(limit)
    result = await session.execute(query)
    deliveries = list(result.scalars().all())

    return deliveries, total
