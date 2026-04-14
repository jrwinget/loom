import socket
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID

import httpx
import pytest_asyncio

from loom.config import Settings, get_settings
from loom.dependencies import get_db_session
from loom.models.plugin import Plugin, Webhook, WebhookDelivery
from loom.security.auth import create_access_token

# fixed uuids
_ADMIN_ID = UUID("01912345-6789-7abc-8def-0123456789ab")
_USER_ID = UUID("01912345-6789-7abc-8def-0123456789cd")
_PLUGIN_ID = UUID("01912345-6789-7abc-8def-0123456789ef")
_WEBHOOK_ID = UUID("01912345-6789-7abc-8def-012345678910")
_DELIVERY_ID = UUID("01912345-6789-7abc-8def-012345678920")

_NOW = datetime(2025, 1, 1, tzinfo=UTC)

# module path prefix for patching
_SVC = "loom.api.v1.plugins"


class _StubSession:
    """minimal stub session for dependency override."""

    async def execute(self, stmt):  # type: ignore[no-untyped-def]
        return MagicMock()

    def add(self, obj):  # type: ignore[no-untyped-def]
        pass

    async def flush(self) -> None:
        pass

    async def commit(self) -> None:
        pass

    async def refresh(self, obj):  # type: ignore[no-untyped-def]
        pass

    async def delete(self, obj):  # type: ignore[no-untyped-def]
        pass


def _make_plugin(
    *,
    plugin_id: UUID = _PLUGIN_ID,
    name: str = "test-plugin",
    plugin_type: str = "webhook",
) -> MagicMock:
    """build a mock plugin."""
    p = MagicMock(spec=Plugin)
    p.id = plugin_id
    p.name = name
    p.description = "a test plugin"
    p.version = "1.0.0"
    p.plugin_type = plugin_type
    p.is_enabled = True
    p.config = None
    p.created_by = _ADMIN_ID
    p.created_at = _NOW
    p.updated_at = _NOW
    return p


def _make_webhook(
    *,
    webhook_id: UUID = _WEBHOOK_ID,
    plugin_id: UUID = _PLUGIN_ID,
) -> MagicMock:
    """build a mock webhook."""
    w = MagicMock(spec=Webhook)
    w.id = webhook_id
    w.plugin_id = plugin_id
    w.url = "https://example.com/hook"
    w.events = ["asset.uploaded"]
    w.is_active = True
    w.last_triggered_at = None
    w.failure_count = 0
    w.created_at = _NOW
    w.updated_at = _NOW
    return w


def _make_delivery(
    *,
    delivery_id: UUID = _DELIVERY_ID,
) -> MagicMock:
    """build a mock delivery."""
    d = MagicMock(spec=WebhookDelivery)
    d.id = delivery_id
    d.event_type = "asset.uploaded"
    d.status_code = 200
    d.delivered_at = _NOW
    d.created_at = _NOW
    return d


def _create_app(settings: Settings) -> object:
    """build a test app with stub db session."""
    get_settings.cache_clear()

    with patch(
        "loom.config.get_settings",
        return_value=settings,
    ):
        from loom.main import create_app

        application = create_app()

    async def override_db():  # type: ignore[no-untyped-def]
        yield _StubSession()

    application.dependency_overrides[get_db_session] = override_db
    # prevent audit middleware from writing to db
    application.state.db_session_factory = None

    return application


@pytest_asyncio.fixture
def mock_settings() -> Settings:
    """override settings for tests."""
    return Settings(
        secret_key=("test-secret-key-that-is-long-enough-for-validation"),
        access_token_expire_minutes=15,
        refresh_token_expire_days=7,
        database_url="sqlite+aiosqlite:///",
    )


def _auth_header(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def test_create_plugin(
    mock_settings: Settings,
) -> None:
    """admin can create a plugin."""
    app = _create_app(mock_settings)
    plugin = _make_plugin()

    with (
        patch(
            "loom.security.auth.get_settings",
            return_value=mock_settings,
        ),
        patch(
            f"{_SVC}.create_plugin",
            new_callable=AsyncMock,
            return_value=plugin,
        ),
    ):
        token = create_access_token(str(_ADMIN_ID), "admin")
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://testserver",
        ) as ac:
            resp = await ac.post(
                "/api/v1/plugins",
                json={
                    "name": "test-plugin",
                    "version": "1.0.0",
                    "plugin_type": "webhook",
                },
                headers=_auth_header(token),
            )

    assert resp.status_code == 201
    data = resp.json()
    assert data["name"] == "test-plugin"
    assert data["plugin_type"] == "webhook"


async def test_non_admin_cannot_create_plugin(
    mock_settings: Settings,
) -> None:
    """non-admin gets 403 on plugin creation."""
    app = _create_app(mock_settings)

    with patch(
        "loom.security.auth.get_settings",
        return_value=mock_settings,
    ):
        token = create_access_token(str(_USER_ID), "analyst")
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://testserver",
        ) as ac:
            resp = await ac.post(
                "/api/v1/plugins",
                json={
                    "name": "test",
                    "version": "1.0.0",
                    "plugin_type": "webhook",
                },
                headers=_auth_header(token),
            )

    assert resp.status_code == 403


async def test_list_plugins(
    mock_settings: Settings,
) -> None:
    """any authenticated user can list plugins."""
    app = _create_app(mock_settings)
    plugin = _make_plugin()

    with (
        patch(
            "loom.security.auth.get_settings",
            return_value=mock_settings,
        ),
        patch(
            f"{_SVC}.list_plugins",
            new_callable=AsyncMock,
            return_value=([plugin], 1),
        ),
    ):
        token = create_access_token(str(_USER_ID), "analyst")
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://testserver",
        ) as ac:
            resp = await ac.get(
                "/api/v1/plugins",
                headers=_auth_header(token),
            )

    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 1
    assert len(data["items"]) == 1


async def test_get_plugin_detail(
    mock_settings: Settings,
) -> None:
    """get plugin detail returns plugin."""
    app = _create_app(mock_settings)
    plugin = _make_plugin()

    with (
        patch(
            "loom.security.auth.get_settings",
            return_value=mock_settings,
        ),
        patch(
            f"{_SVC}.get_plugin",
            new_callable=AsyncMock,
            return_value=plugin,
        ),
    ):
        token = create_access_token(str(_USER_ID), "analyst")
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://testserver",
        ) as ac:
            resp = await ac.get(
                f"/api/v1/plugins/{_PLUGIN_ID}",
                headers=_auth_header(token),
            )

    assert resp.status_code == 200
    assert resp.json()["name"] == "test-plugin"


async def test_get_plugin_not_found(
    mock_settings: Settings,
) -> None:
    """missing plugin returns 404."""
    app = _create_app(mock_settings)

    with (
        patch(
            "loom.security.auth.get_settings",
            return_value=mock_settings,
        ),
        patch(
            f"{_SVC}.get_plugin",
            new_callable=AsyncMock,
            return_value=None,
        ),
    ):
        token = create_access_token(str(_USER_ID), "analyst")
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://testserver",
        ) as ac:
            resp = await ac.get(
                f"/api/v1/plugins/{_PLUGIN_ID}",
                headers=_auth_header(token),
            )

    assert resp.status_code == 404


async def test_delete_plugin_admin(
    mock_settings: Settings,
) -> None:
    """admin can delete a plugin."""
    app = _create_app(mock_settings)

    with (
        patch(
            "loom.security.auth.get_settings",
            return_value=mock_settings,
        ),
        patch(
            f"{_SVC}.delete_plugin",
            new_callable=AsyncMock,
            return_value=True,
        ),
    ):
        token = create_access_token(str(_ADMIN_ID), "admin")
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://testserver",
        ) as ac:
            resp = await ac.delete(
                f"/api/v1/plugins/{_PLUGIN_ID}",
                headers=_auth_header(token),
            )

    assert resp.status_code == 204


async def test_create_webhook(
    mock_settings: Settings,
) -> None:
    """admin can create a webhook for a plugin."""
    app = _create_app(mock_settings)
    plugin = _make_plugin()
    webhook = _make_webhook()

    with (
        patch(
            "loom.security.auth.get_settings",
            return_value=mock_settings,
        ),
        patch(
            f"{_SVC}.get_plugin",
            new_callable=AsyncMock,
            return_value=plugin,
        ),
        patch(
            f"{_SVC}.create_webhook",
            new_callable=AsyncMock,
            return_value=webhook,
        ),
    ):
        token = create_access_token(str(_ADMIN_ID), "admin")
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://testserver",
        ) as ac:
            resp = await ac.post(
                f"/api/v1/plugins/{_PLUGIN_ID}/webhooks",
                json={
                    "plugin_id": str(_PLUGIN_ID),
                    "url": "https://example.com/hook",
                    "events": ["asset.uploaded"],
                },
                headers=_auth_header(token),
            )

    assert resp.status_code == 201
    data = resp.json()
    assert data["url"] == "https://example.com/hook"


async def test_list_webhooks(
    mock_settings: Settings,
) -> None:
    """list webhooks for a plugin."""
    app = _create_app(mock_settings)
    webhook = _make_webhook()

    with (
        patch(
            "loom.security.auth.get_settings",
            return_value=mock_settings,
        ),
        patch(
            f"{_SVC}.list_webhooks",
            new_callable=AsyncMock,
            return_value=([webhook], 1),
        ),
    ):
        token = create_access_token(str(_USER_ID), "analyst")
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://testserver",
        ) as ac:
            resp = await ac.get(
                f"/api/v1/plugins/{_PLUGIN_ID}/webhooks",
                headers=_auth_header(token),
            )

    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 1


async def test_delivery_log(
    mock_settings: Settings,
) -> None:
    """get delivery log for a webhook."""
    app = _create_app(mock_settings)
    webhook = _make_webhook()
    delivery = _make_delivery()

    with (
        patch(
            "loom.security.auth.get_settings",
            return_value=mock_settings,
        ),
        patch(
            f"{_SVC}.get_webhook",
            new_callable=AsyncMock,
            return_value=webhook,
        ),
        patch(
            f"{_SVC}.get_deliveries",
            new_callable=AsyncMock,
            return_value=([delivery], 1),
        ),
    ):
        token = create_access_token(str(_USER_ID), "analyst")
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://testserver",
        ) as ac:
            resp = await ac.get(
                f"/api/v1/plugins/{_PLUGIN_ID}"
                f"/webhooks/{_WEBHOOK_ID}/deliveries",
                headers=_auth_header(token),
            )

    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 1
    assert data["items"][0]["event_type"] == "asset.uploaded"


async def test_non_admin_cannot_delete_plugin(
    mock_settings: Settings,
) -> None:
    """non-admin gets 403 on plugin deletion."""
    app = _create_app(mock_settings)

    with patch(
        "loom.security.auth.get_settings",
        return_value=mock_settings,
    ):
        token = create_access_token(str(_USER_ID), "analyst")
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://testserver",
        ) as ac:
            resp = await ac.delete(
                f"/api/v1/plugins/{_PLUGIN_ID}",
                headers=_auth_header(token),
            )

    assert resp.status_code == 403


async def test_update_plugin_changes_fields(
    mock_settings: Settings,
) -> None:
    """admin can update plugin fields."""
    app = _create_app(mock_settings)
    plugin = _make_plugin()
    updated_plugin = _make_plugin(name="updated-plugin")

    with (
        patch(
            "loom.security.auth.get_settings",
            return_value=mock_settings,
        ),
        patch(
            f"{_SVC}.get_plugin",
            new_callable=AsyncMock,
            return_value=plugin,
        ),
        patch(
            f"{_SVC}.update_plugin",
            new_callable=AsyncMock,
            return_value=updated_plugin,
        ),
    ):
        token = create_access_token(str(_ADMIN_ID), "admin")
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://testserver",
        ) as ac:
            resp = await ac.patch(
                f"/api/v1/plugins/{_PLUGIN_ID}",
                json={"name": "updated-plugin"},
                headers=_auth_header(token),
            )

    assert resp.status_code == 200
    assert resp.json()["name"] == "updated-plugin"


async def test_delete_plugin_removes_it(
    mock_settings: Settings,
) -> None:
    """delete plugin returns 204 when successful."""
    app = _create_app(mock_settings)

    with (
        patch(
            "loom.security.auth.get_settings",
            return_value=mock_settings,
        ),
        patch(
            f"{_SVC}.delete_plugin",
            new_callable=AsyncMock,
            return_value=True,
        ),
    ):
        token = create_access_token(str(_ADMIN_ID), "admin")
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://testserver",
        ) as ac:
            resp = await ac.delete(
                f"/api/v1/plugins/{_PLUGIN_ID}",
                headers=_auth_header(token),
            )

    assert resp.status_code == 204


async def test_update_webhook(
    mock_settings: Settings,
) -> None:
    """admin can update a webhook."""
    app = _create_app(mock_settings)
    webhook = _make_webhook()
    updated = _make_webhook()
    updated.url = "https://updated.example.com/hook"

    # mock dns to avoid resolution failures in test env
    fake_addr = [
        (socket.AF_INET, socket.SOCK_STREAM, 0, "",
         ("93.184.216.34", 443)),
    ]
    with (
        patch(
            "loom.security.auth.get_settings",
            return_value=mock_settings,
        ),
        patch(
            f"{_SVC}.get_webhook",
            new_callable=AsyncMock,
            return_value=webhook,
        ),
        patch(
            f"{_SVC}.update_webhook",
            new_callable=AsyncMock,
            return_value=updated,
        ),
        patch("socket.getaddrinfo", return_value=fake_addr),
    ):
        token = create_access_token(str(_ADMIN_ID), "admin")
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://testserver",
        ) as ac:
            resp = await ac.patch(
                f"/api/v1/plugins/{_PLUGIN_ID}/webhooks/{_WEBHOOK_ID}",
                json={"url": "https://updated.example.com/hook"},
                headers=_auth_header(token),
            )

    assert resp.status_code == 200
    assert resp.json()["url"] == "https://updated.example.com/hook"


async def test_delete_webhook(
    mock_settings: Settings,
) -> None:
    """admin can delete a webhook."""
    app = _create_app(mock_settings)
    webhook = _make_webhook()

    with (
        patch(
            "loom.security.auth.get_settings",
            return_value=mock_settings,
        ),
        patch(
            f"{_SVC}.get_webhook",
            new_callable=AsyncMock,
            return_value=webhook,
        ),
        patch(
            f"{_SVC}.delete_webhook",
            new_callable=AsyncMock,
            return_value=True,
        ),
    ):
        token = create_access_token(str(_ADMIN_ID), "admin")
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://testserver",
        ) as ac:
            resp = await ac.delete(
                f"/api/v1/plugins/{_PLUGIN_ID}/webhooks/{_WEBHOOK_ID}",
                headers=_auth_header(token),
            )

    assert resp.status_code == 204


async def test_delivery_log_empty(
    mock_settings: Settings,
) -> None:
    """delivery log returns empty list initially."""
    app = _create_app(mock_settings)
    webhook = _make_webhook()

    with (
        patch(
            "loom.security.auth.get_settings",
            return_value=mock_settings,
        ),
        patch(
            f"{_SVC}.get_webhook",
            new_callable=AsyncMock,
            return_value=webhook,
        ),
        patch(
            f"{_SVC}.get_deliveries",
            new_callable=AsyncMock,
            return_value=([], 0),
        ),
    ):
        token = create_access_token(str(_USER_ID), "analyst")
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://testserver",
        ) as ac:
            resp = await ac.get(
                f"/api/v1/plugins/{_PLUGIN_ID}"
                f"/webhooks/{_WEBHOOK_ID}/deliveries",
                headers=_auth_header(token),
            )

    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 0
    assert data["items"] == []


async def test_non_admin_cannot_update_plugin(
    mock_settings: Settings,
) -> None:
    """non-admin gets 403 on plugin update."""
    app = _create_app(mock_settings)

    with patch(
        "loom.security.auth.get_settings",
        return_value=mock_settings,
    ):
        token = create_access_token(str(_USER_ID), "analyst")
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://testserver",
        ) as ac:
            resp = await ac.patch(
                f"/api/v1/plugins/{_PLUGIN_ID}",
                json={"name": "nope"},
                headers=_auth_header(token),
            )

    assert resp.status_code == 403
