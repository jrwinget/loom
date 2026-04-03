import logging
import uuid
from collections.abc import AsyncIterator, MutableMapping
from contextlib import asynccontextmanager
from typing import Any

import structlog
from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from minio import Minio
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from loom.api.router import api_router
from loom.config import get_settings
from loom.observability import setup_db_telemetry, setup_telemetry
from loom.security.audit import AuditMiddleware
from loom.security.csrf import CSRFMiddleware
from loom.security.rate_limit import limiter


def _add_otel_context(
    _logger: Any,
    _method: str,
    event_dict: MutableMapping[str, Any],
) -> MutableMapping[str, Any]:
    """inject otel trace/span ids into structlog events."""
    try:
        from opentelemetry import trace

        span = trace.get_current_span()
        ctx = span.get_span_context()
        if ctx and ctx.trace_id:
            event_dict["trace_id"] = format(ctx.trace_id, "032x")
            event_dict["span_id"] = format(ctx.span_id, "016x")
    except Exception:  # noqa: S110
        pass  # otel may not be configured; safe to skip
    return event_dict


def _configure_logging(log_level: str) -> None:
    """configure structlog for json output."""
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            _add_otel_context,
            structlog.processors.StackInfoRenderer(),
            structlog.dev.set_exc_info,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(
            logging.getLevelName(log_level.upper())
        ),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )


@asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncIterator[None]:
    """manage startup and shutdown resources."""
    settings = get_settings()
    log = structlog.get_logger()

    # validate secret key before anything else
    try:
        settings.validate_secret_key()
    except ValueError as exc:
        logging.critical("configuration error: %s", exc)
        raise

    # database
    engine = create_async_engine(
        settings.database_url,
        echo=settings.debug,
        pool_size=settings.db_pool_size,
        max_overflow=settings.db_max_overflow,
        pool_recycle=settings.db_pool_recycle,
        pool_pre_ping=settings.db_pool_pre_ping,
        pool_timeout=settings.db_pool_timeout,
    )
    session_factory = async_sessionmaker(
        engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )
    app.state.db_engine = engine
    app.state.db_session_factory = session_factory

    # trace database queries when otel is active
    if settings.otel_enabled:
        setup_db_telemetry(engine.sync_engine)

    # minio / object storage
    minio_client = Minio(
        settings.minio_endpoint,
        access_key=settings.minio_access_key,
        secret_key=settings.minio_secret_key,
        secure=settings.minio_secure,
    )
    app.state.minio_client = minio_client

    await log.ainfo(
        "startup complete",
        database=settings.database_url,
        minio=settings.minio_endpoint,
    )

    yield

    # shutdown
    await engine.dispose()
    await log.ainfo("shutdown complete")


def create_app() -> FastAPI:
    """application factory."""
    settings = get_settings()
    _configure_logging(settings.log_level)

    application = FastAPI(
        title="Loom",
        description="Evidence operating system",
        version="0.1.0",
        lifespan=_lifespan,
        debug=settings.debug,
    )

    # rate limiter
    application.state.limiter = limiter
    from slowapi import _rate_limit_exceeded_handler
    from slowapi.errors import RateLimitExceeded

    application.add_exception_handler(
        RateLimitExceeded,
        _rate_limit_exceeded_handler,  # type: ignore[arg-type]
    )

    # cors
    application.add_middleware(
        CORSMiddleware,
        allow_origins=["*"] if settings.debug else [],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # request-id middleware
    @application.middleware("http")
    async def add_request_id(request: Request, call_next: object) -> Response:
        request_id = str(uuid.uuid4())
        response: Response = await call_next(request)  # type: ignore[operator]
        response.headers["X-Request-Id"] = request_id
        return response

    # routes
    application.include_router(api_router, prefix="/api/v1")

    # csrf double-submit validation
    application.add_middleware(CSRFMiddleware)

    # audit middleware
    application.add_middleware(AuditMiddleware)

    # observability (opt-in via LOOM_OTEL_ENABLED=true)
    setup_telemetry(application, settings)

    return application


app = create_app()
