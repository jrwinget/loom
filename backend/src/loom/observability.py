"""opentelemetry instrumentation for the loom backend.

all otel imports are guarded so the app degrades gracefully
when the sdk is not installed.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from fastapi import FastAPI

    from loom.config import Settings

logger = logging.getLogger(__name__)

_HAS_OTEL_SDK = False
_HAS_OTLP_EXPORTER = False
_HAS_OTEL_FASTAPI = False
_HAS_OTEL_SQLALCHEMY = False

try:
    from opentelemetry import metrics, trace
    from opentelemetry.sdk.metrics import MeterProvider
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import (
        ConsoleSpanExporter,
        SimpleSpanProcessor,
    )

    _HAS_OTEL_SDK = True
except ImportError:  # pragma: no cover
    pass

try:
    from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import (
        OTLPSpanExporter,
    )

    _HAS_OTLP_EXPORTER = True
except ImportError:  # pragma: no cover
    pass

try:
    from opentelemetry.instrumentation.fastapi import (
        FastAPIInstrumentor,
    )

    _HAS_OTEL_FASTAPI = True
except ImportError:  # pragma: no cover
    pass

try:
    from opentelemetry.instrumentation.sqlalchemy import (
        SQLAlchemyInstrumentor,
    )

    _HAS_OTEL_SQLALCHEMY = True
except ImportError:  # pragma: no cover
    pass


def setup_telemetry(app: FastAPI, settings: Settings) -> bool:
    """conditionally configure opentelemetry tracing and metrics.

    returns True if instrumentation was activated, False otherwise.
    does nothing if otel_enabled is False or the sdk is missing.
    """
    if not settings.otel_enabled:
        logger.debug("otel disabled, skipping setup")
        return False

    if not _HAS_OTEL_SDK:
        logger.warning(
            "otel_enabled=True but opentelemetry-sdk is not "
            "installed; skipping instrumentation"
        )
        return False

    resource = Resource.create(
        {
            "service.name": settings.otel_service_name,
            "service.version": "0.1.0",
        }
    )

    # tracer provider
    tracer_provider = TracerProvider(resource=resource)

    if _HAS_OTLP_EXPORTER and settings.otel_exporter_endpoint:
        exporter = OTLPSpanExporter(
            endpoint=settings.otel_exporter_endpoint,
            insecure=True,
        )
        tracer_provider.add_span_processor(SimpleSpanProcessor(exporter))
    else:
        # fall back to console exporter for local dev
        tracer_provider.add_span_processor(
            SimpleSpanProcessor(ConsoleSpanExporter())
        )

    trace.set_tracer_provider(tracer_provider)

    # meter provider
    meter_provider = MeterProvider(resource=resource)
    metrics.set_meter_provider(meter_provider)

    # fastapi auto-instrumentation (request count, duration,
    # active requests are handled automatically)
    if _HAS_OTEL_FASTAPI:
        FastAPIInstrumentor.instrument_app(app)
        logger.info("fastapi otel instrumentation enabled")
    else:
        logger.warning(
            "opentelemetry-instrumentation-fastapi not "
            "installed; skipping route instrumentation"
        )

    logger.info(
        "otel telemetry initialized (service=%s, endpoint=%s)",
        settings.otel_service_name,
        settings.otel_exporter_endpoint,
    )
    return True


def setup_db_telemetry(engine: Any) -> bool:
    """instrument sqlalchemy engine for query tracing.

    call after the engine is created in lifespan.
    returns True if instrumentation was activated.
    """
    if not _HAS_OTEL_SQLALCHEMY:
        return False

    SQLAlchemyInstrumentor().instrument(engine=engine)
    logger.info("sqlalchemy otel instrumentation enabled")
    return True


def get_tracer(name: str) -> Any:
    """return an otel tracer (no-op when sdk is absent)."""
    if _HAS_OTEL_SDK:
        return trace.get_tracer(name)
    # return a no-op stand-in
    return None


def get_meter(name: str) -> Any:
    """return an otel meter (no-op when sdk is absent)."""
    if _HAS_OTEL_SDK:
        return metrics.get_meter(name)
    return None
