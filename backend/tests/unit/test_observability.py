"""tests for opentelemetry observability module."""

from unittest.mock import MagicMock, patch

from fastapi import FastAPI

from loom.config import Settings
from loom.observability import (
    get_meter,
    get_tracer,
    setup_db_telemetry,
    setup_telemetry,
)


def _make_settings(**overrides: object) -> Settings:
    """create test settings with safe defaults."""
    defaults: dict[str, object] = {
        "secret_key": ("test-secret-key-that-is-long-enough-for-validation"),
        "debug": False,
        "log_level": "info",
        "otel_enabled": False,
        "otel_service_name": "loom-test",
        "otel_exporter_endpoint": "http://localhost:4317",
    }
    defaults.update(overrides)
    return Settings(**defaults)  # type: ignore[arg-type]


class TestSetupTelemetryDisabled:
    """telemetry does nothing when disabled."""

    def test_returns_false_when_disabled(self) -> None:
        """setup_telemetry returns False when otel_enabled=False."""
        app = FastAPI()
        settings = _make_settings(otel_enabled=False)
        result = setup_telemetry(app, settings)
        assert result is False

    def test_no_instrumentation_applied(self) -> None:
        """app should have no otel middleware when disabled."""
        app = FastAPI()
        settings = _make_settings(otel_enabled=False)
        setup_telemetry(app, settings)
        # no extra middleware should be added
        assert len(app.user_middleware) == 0


class TestSetupTelemetryEnabled:
    """telemetry activates when enabled with sdk present."""

    def test_returns_true_when_enabled(self) -> None:
        """setup_telemetry returns True with sdk present."""
        app = FastAPI()
        settings = _make_settings(otel_enabled=True)
        result = setup_telemetry(app, settings)
        assert result is True

    def test_instruments_fastapi_app(self) -> None:
        """fastapi instrumentor is called on the app."""
        app = FastAPI()
        settings = _make_settings(otel_enabled=True)
        with patch("loom.observability.FastAPIInstrumentor") as mock_instr:
            with patch("loom.observability._HAS_OTEL_FASTAPI", True):
                setup_telemetry(app, settings)
            mock_instr.instrument_app.assert_called_once_with(app)


class TestSetupTelemetryMissingSdk:
    """graceful degradation when sdk is not installed."""

    def test_returns_false_without_sdk(self) -> None:
        """returns False when otel sdk is missing."""
        app = FastAPI()
        settings = _make_settings(otel_enabled=True)
        with patch("loom.observability._HAS_OTEL_SDK", False):
            result = setup_telemetry(app, settings)
        assert result is False


class TestSetupDbTelemetry:
    """database instrumentation."""

    def test_returns_false_without_instrumentation(self) -> None:
        """returns False when sqlalchemy instrumentation missing."""
        with patch("loom.observability._HAS_OTEL_SQLALCHEMY", False):
            result = setup_db_telemetry(MagicMock())
        assert result is False

    def test_instruments_engine(self) -> None:
        """calls SQLAlchemyInstrumentor when available."""
        mock_engine = MagicMock()
        mock_instrumentor = MagicMock()
        with (
            patch("loom.observability._HAS_OTEL_SQLALCHEMY", True),
            patch(
                "loom.observability.SQLAlchemyInstrumentor",
                create=True,
                return_value=mock_instrumentor,
            ),
        ):
            result = setup_db_telemetry(mock_engine)
        assert result is True
        mock_instrumentor.instrument.assert_called_once_with(engine=mock_engine)


class TestGetTracer:
    """tracer convenience wrapper."""

    def test_returns_tracer_with_sdk(self) -> None:
        """returns a tracer object when sdk is present."""
        tracer = get_tracer("test")
        assert tracer is not None

    def test_returns_none_without_sdk(self) -> None:
        """returns None when sdk is missing."""
        with patch("loom.observability._HAS_OTEL_SDK", False):
            tracer = get_tracer("test")
        assert tracer is None


class TestGetMeter:
    """meter convenience wrapper."""

    def test_returns_meter_with_sdk(self) -> None:
        """returns a meter object when sdk is present."""
        meter = get_meter("test")
        assert meter is not None

    def test_returns_none_without_sdk(self) -> None:
        """returns None when sdk is missing."""
        with patch("loom.observability._HAS_OTEL_SDK", False):
            meter = get_meter("test")
        assert meter is None
