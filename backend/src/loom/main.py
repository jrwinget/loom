import logging
import logging.handlers
import sys
import uuid
from collections.abc import AsyncIterator, Callable, MutableMapping
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import structlog
from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from minio import Minio
from sqlalchemy import event
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from structlog.typing import Processor

from loom import __version__
from loom.api.router import api_router
from loom.config import Settings, get_settings
from loom.observability import setup_db_telemetry, setup_telemetry
from loom.security.audit import AuditMiddleware
from loom.security.csrf import CSRFMiddleware
from loom.security.rate_limit import limiter
from loom.services.log_redaction import redact_sensitive
from loom.services.storage_backends import build_storage_backend


def _enable_sqlite_foreign_keys(dbapi_conn: Any, _record: Any) -> None:
    """turn on per-connection foreign-key enforcement for sqlite."""
    cursor = dbapi_conn.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


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


# rotation caps for the lite-profile backend log file. sized so the
# full set stays around 30 mb — small enough for a diagnostics zip,
# large enough to cover days of field use.
_LOG_FILE_MAX_BYTES = 5 * 1024 * 1024
_LOG_FILE_BACKUPS = 5


class _TeeLogger:
    """print-style logger that also appends lines to a rotating file.

    stdout stays authoritative — the desktop shell drains it into
    its own log — while the handler gives the lite profile a local
    file that survives shell restarts (issue #285).
    """

    def __init__(self, handler: logging.Handler) -> None:
        self._handler = handler

    def msg(self, message: str) -> None:
        sys.stdout.write(message + "\n")
        sys.stdout.flush()
        self._handler.handle(logging.makeLogRecord({"msg": message}))

    log = debug = info = warn = warning = msg
    error = err = critical = exception = fatal = failure = msg


def _lite_logger_factory(
    data_dir: Path,
) -> Callable[..., _TeeLogger] | None:
    """tee-to-file logger factory, or None when the dir is unusable.

    log files must never block startup: an unwritable data dir
    degrades to stdout-only logging instead of raising.
    """
    try:
        # "logs" matches storage_relocation._LOGS_DIRNAME and the
        # diagnostics allowlist in desktop/src-tauri/src/main.rs.
        logs_dir = data_dir / "logs"
        logs_dir.mkdir(parents=True, exist_ok=True)
        handler = logging.handlers.RotatingFileHandler(
            logs_dir / "backend.jsonl",
            maxBytes=_LOG_FILE_MAX_BYTES,
            backupCount=_LOG_FILE_BACKUPS,
            encoding="utf-8",
            delay=True,
        )
    except OSError:
        return None
    tee = _TeeLogger(handler)

    def factory(*_args: object) -> _TeeLogger:
        return tee

    return factory


def _configure_logging(settings: Settings) -> None:
    """configure structlog for json output.

    server profile: json lines to stdout, unchanged. lite profile:
    the same lines are scrubbed of emails and home paths, then teed
    into a rotating <data_dir>/logs/backend.jsonl so the desktop
    shell can bundle them into diagnostics exports (issue #285).
    """
    processors: list[Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        _add_otel_context,
        structlog.processors.StackInfoRenderer(),
        structlog.dev.set_exc_info,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
    ]
    logger_factory: Callable[..., Any] = structlog.PrintLoggerFactory()
    if settings.is_lite:
        processors.append(redact_sensitive)
        file_factory = _lite_logger_factory(settings.resolved_data_dir())
        if file_factory is not None:
            logger_factory = file_factory
    processors.append(structlog.processors.JSONRenderer())
    structlog.configure(
        processors=processors,
        wrapper_class=structlog.make_filtering_bound_logger(
            logging.getLevelName(settings.log_level.upper())
        ),
        context_class=dict,
        logger_factory=logger_factory,
        cache_logger_on_first_use=True,
    )


@asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncIterator[None]:
    """manage startup and shutdown resources."""
    settings = get_settings()
    log = structlog.get_logger()

    # validate secret key and deployment profile before anything else
    try:
        settings.validate_secret_key()
        settings.validate_deployment_profile()
        settings.validate_production_settings()
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
    # sqlite (lite profile) enforces foreign keys only when asked, per
    # connection; without this a case purge would orphan its assets and
    # timeline instead of cascading. postgres enforces natively.
    if settings.database_url.startswith("sqlite"):
        event.listen(engine.sync_engine, "connect", _enable_sqlite_foreign_keys)

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

    # object storage. the backend is the single source of truth for
    # every caller; the minio client is retained on app state only
    # for the health check and a handful of legacy call sites.
    storage_backend = build_storage_backend(settings)
    app.state.storage_backend = storage_backend

    # reap upload temp files orphaned by a crash
    from loom.services.streaming_upload import cleanup_stale_uploads

    cleanup_stale_uploads()

    if not settings.is_lite:
        minio_client = Minio(
            settings.minio_endpoint,
            access_key=settings.minio_access_key,
            secret_key=settings.minio_secret_key,
            secure=settings.minio_secure,
        )
        app.state.minio_client = minio_client
    else:
        app.state.minio_client = None

    await log.ainfo(
        "startup complete",
        database=settings.database_url,
        deployment_profile=settings.deployment_profile,
    )

    yield

    # shutdown. let in-flight lite in-process workflows finish (best
    # effort) before tearing the engine down; activities are
    # idempotent, so any that don't finish can be re-dispatched.
    from loom.workflows.dispatch import drain_background_tasks

    await drain_background_tasks()
    await engine.dispose()
    await log.ainfo("shutdown complete")


def create_app() -> FastAPI:
    """application factory."""
    settings = get_settings()
    _configure_logging(settings)

    application = FastAPI(
        title="Loom",
        description="Evidence operating system",
        version=__version__,
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
        allow_origins=(["*"] if settings.debug else settings.cors_origins),
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # csrf double-submit cookie validation
    application.add_middleware(CSRFMiddleware)

    # request-id + security headers middleware
    @application.middleware("http")
    async def add_request_id(request: Request, call_next: object) -> Response:
        request_id = str(uuid.uuid4())
        response: Response = await call_next(request)  # type: ignore[operator]
        response.headers["X-Request-Id"] = request_id
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-XSS-Protection"] = "0"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = (
            "camera=(), microphone=(), geolocation=()"
        )
        return response

    # routes
    application.include_router(api_router, prefix="/api/v1")

    # audit middleware
    application.add_middleware(AuditMiddleware)

    # prometheus metrics endpoint
    from prometheus_fastapi_instrumentator import Instrumentator

    from loom.metrics import install_route_name_compat

    install_route_name_compat()
    Instrumentator().instrument(application).expose(
        application, endpoint="/metrics", include_in_schema=False
    )

    # observability (opt-in via LOOM_OTEL_ENABLED=true)
    setup_telemetry(application, settings)

    return application


app = create_app()
