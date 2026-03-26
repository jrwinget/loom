import logging
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

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
from loom.security.audit import AuditMiddleware


def _configure_logging(log_level: str) -> None:
    """configure structlog for json output."""
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
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

    # database
    engine = create_async_engine(
        settings.database_url,
        echo=settings.debug,
    )
    session_factory = async_sessionmaker(
        engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )
    app.state.db_engine = engine
    app.state.db_session_factory = session_factory

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

    # audit middleware
    application.add_middleware(AuditMiddleware)

    return application


app = create_app()
