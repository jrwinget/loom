"""unit tests for runtime AI engine configuration."""

from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from loom.models.app_setting import AppSetting
from loom.models.base import Base
from loom.services.ai_config import (
    load_ai_config,
    save_ai_config,
    validate_endpoint,
)


@pytest_asyncio.fixture
async def session() -> AsyncIterator[AsyncSession]:
    engine = create_async_engine("sqlite+aiosqlite://")
    async with engine.begin() as conn:
        await conn.run_sync(
            Base.metadata.create_all, tables=[AppSetting.__table__]
        )
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as s:
        yield s
    await engine.dispose()


async def test_defaults_when_unset(session: AsyncSession) -> None:
    config = await load_ai_config(session)
    assert config.transcription_engine == "local"
    assert config.cloud_transcription_enabled is False


async def test_save_and_reload_round_trip(session: AsyncSession) -> None:
    await save_ai_config(
        session,
        {
            "transcription_engine": "cloud",
            "api_key": "sk-test",
            "api_base_url": "https://api.openai.com/v1",
            "transcription_model": "whisper-1",
        },
    )
    config = await load_ai_config(session)
    assert config.transcription_engine == "cloud"
    assert config.api_key == "sk-test"
    assert config.cloud_transcription_enabled is True


async def test_partial_update_preserves_key(session: AsyncSession) -> None:
    await save_ai_config(
        session,
        {"transcription_engine": "cloud", "api_key": "sk-keep"},
    )
    # a later update that omits api_key must not wipe it
    await save_ai_config(session, {"transcription_model": "whisper-large"})
    config = await load_ai_config(session)
    assert config.api_key == "sk-keep"
    assert config.transcription_model == "whisper-large"


async def test_rejects_unknown_engine(session: AsyncSession) -> None:
    with pytest.raises(ValueError, match="transcription_engine"):
        await save_ai_config(session, {"transcription_engine": "magic"})


async def test_cloud_rejects_internal_endpoint(
    session: AsyncSession,
) -> None:
    with pytest.raises(ValueError, match=r"(?i)endpoint"):
        await save_ai_config(
            session,
            {
                "transcription_engine": "cloud",
                "api_base_url": "http://localhost:8000/v1",
                "api_key": "sk-x",
            },
        )


@pytest.mark.parametrize(
    "bad",
    [
        "http://localhost/v1",
        "http://127.0.0.1/v1",
        "https://10.0.0.5/v1",
        "ftp://example.com/v1",
        "not-a-url",
    ],
)
def test_validate_endpoint_rejects(bad: str) -> None:
    with pytest.raises(ValueError):
        validate_endpoint(bad)


@pytest.mark.parametrize(
    "ok",
    ["https://api.openai.com/v1", "https://transcribe.example.com/v1"],
)
def test_validate_endpoint_accepts_public(ok: str) -> None:
    validate_endpoint(ok)  # no raise
