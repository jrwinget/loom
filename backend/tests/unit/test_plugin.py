import pytest
from pydantic import ValidationError

from loom.schemas.plugin import (
    PLUGIN_TYPES,
    WEBHOOK_EVENT_TYPES,
    PluginCreate,
    PluginUpdate,
    WebhookCreate,
    WebhookUpdate,
)


class TestPluginTypeValidation:
    """plugin_type field validation."""

    @pytest.mark.parametrize("ptype", PLUGIN_TYPES)
    def test_valid_plugin_types(self, ptype: str) -> None:
        """all valid plugin types are accepted."""
        schema = PluginCreate(
            name="test",
            version="1.0.0",
            plugin_type=ptype,
        )
        assert schema.plugin_type == ptype

    def test_invalid_plugin_type_rejected(self) -> None:
        """unknown plugin type raises validation error."""
        with pytest.raises(ValidationError):
            PluginCreate(
                name="test",
                version="1.0.0",
                plugin_type="invalid",
            )

    def test_create_with_config(self) -> None:
        """config field is optional on create."""
        schema = PluginCreate(
            name="test",
            version="1.0.0",
            plugin_type="webhook",
            config={"endpoint": "https://example.com"},
        )
        assert schema.config == {"endpoint": "https://example.com"}

    def test_create_config_default_none(self) -> None:
        """config defaults to none."""
        schema = PluginCreate(
            name="test",
            version="1.0.0",
            plugin_type="webhook",
        )
        assert schema.config is None

    def test_update_all_none(self) -> None:
        """update with no fields is valid."""
        schema = PluginUpdate()
        assert schema.description is None
        assert schema.version is None
        assert schema.is_enabled is None
        assert schema.config is None

    def test_name_min_length(self) -> None:
        """name must have at least 1 character."""
        with pytest.raises(ValidationError):
            PluginCreate(
                name="",
                version="1.0.0",
                plugin_type="webhook",
            )


class TestWebhookEventValidation:
    """webhook event type validation."""

    def test_valid_events_accepted(self) -> None:
        """valid event types pass validation."""
        schema = WebhookCreate(
            plugin_id="01912345-6789-7abc-8def-0123456789ab",
            url="https://example.com/hook",
            events=["asset.uploaded", "asset.processed"],
        )
        assert len(schema.events) == 2

    def test_invalid_event_rejected(self) -> None:
        """invalid event type raises validation error."""
        with pytest.raises(ValidationError):
            WebhookCreate(
                plugin_id=("01912345-6789-7abc-8def-0123456789ab"),
                url="https://example.com/hook",
                events=["invalid.event"],
            )

    def test_empty_events_rejected(self) -> None:
        """empty events list raises validation error."""
        with pytest.raises(ValidationError):
            WebhookCreate(
                plugin_id=("01912345-6789-7abc-8def-0123456789ab"),
                url="https://example.com/hook",
                events=[],
            )

    @pytest.mark.parametrize("event", WEBHOOK_EVENT_TYPES)
    def test_all_event_types_valid(self, event: str) -> None:
        """every defined event type is accepted."""
        schema = WebhookCreate(
            plugin_id="01912345-6789-7abc-8def-0123456789ab",
            url="https://example.com/hook",
            events=[event],
        )
        assert schema.events == [event]

    def test_webhook_update_valid_events(self) -> None:
        """update with valid events passes."""
        schema = WebhookUpdate(events=["case.created", "case.archived"])
        assert schema.events == [
            "case.created",
            "case.archived",
        ]

    def test_webhook_update_invalid_events(self) -> None:
        """update with invalid events fails."""
        with pytest.raises(ValidationError):
            WebhookUpdate(events=["bogus.event"])

    def test_webhook_update_none_events(self) -> None:
        """update with none events is valid."""
        schema = WebhookUpdate()
        assert schema.events is None


class TestPluginModel:
    """plugin model instantiation."""

    def test_model_fields(self) -> None:
        """model has expected table name."""
        from loom.models.plugin import Plugin

        assert Plugin.__tablename__ == "plugins"

    def test_webhook_model_fields(self) -> None:
        """webhook model has expected table name."""
        from loom.models.plugin import Webhook

        assert Webhook.__tablename__ == "webhooks"

    def test_delivery_model_fields(self) -> None:
        """delivery model has expected table name."""
        from loom.models.plugin import WebhookDelivery

        assert WebhookDelivery.__tablename__ == "webhook_deliveries"

    def test_models_in_registry(self) -> None:
        """models are registered in models __init__."""
        from loom.models import (
            Plugin,
            Webhook,
            WebhookDelivery,
        )

        assert Plugin is not None
        assert Webhook is not None
        assert WebhookDelivery is not None
