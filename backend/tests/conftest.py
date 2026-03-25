from collections.abc import AsyncIterator

import httpx
import pytest_asyncio
from fastapi import FastAPI

from loom.config import Settings, get_settings
from loom.main import create_app


@pytest_asyncio.fixture
def settings() -> Settings:
    """return test settings override."""
    return Settings(
        database_url=(
            "postgresql+asyncpg://loom:loom_dev@localhost:5432/loom_test"
        ),
        secret_key="test-secret-key",
        debug=True,
        log_level="debug",
    )


@pytest_asyncio.fixture
def app(settings: Settings) -> FastAPI:
    """create app with test config."""
    get_settings.cache_clear()
    application = create_app()
    return application


@pytest_asyncio.fixture
async def client(
    app: FastAPI,
) -> AsyncIterator[httpx.AsyncClient]:
    """async http client pointed at the test app."""
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    ) as ac:
        yield ac
