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
    assert config.provider == ""
    assert config.cloud_transcription_enabled is False


async def test_hosted_provider_round_trip_derives_base_url(
    session: AsyncSession,
) -> None:
    # a user-sent base url is ignored for a hosted provider; the catalog
    # url wins so audio can only go where we expect.
    await save_ai_config(
        session,
        {
            "transcription_engine": "cloud",
            "provider": "openai",
            "api_key": "sk-test",
            "api_base_url": "https://evil.example/v1",
            "transcription_model": "gpt-4o-transcribe",
        },
    )
    config = await load_ai_config(session)
    assert config.provider == "openai"
    assert config.api_base_url == "https://api.openai.com/v1"
    assert config.api_key == "sk-test"
    assert config.cloud_transcription_enabled is True


async def test_partial_update_preserves_key(session: AsyncSession) -> None:
    await save_ai_config(
        session,
        {
            "transcription_engine": "cloud",
            "provider": "openai",
            "api_key": "sk-keep",
            "transcription_model": "whisper-1",
        },
    )
    # a later update that omits api_key must not wipe it
    await save_ai_config(session, {"transcription_model": "gpt-4o-transcribe"})
    config = await load_ai_config(session)
    assert config.api_key == "sk-keep"
    assert config.transcription_model == "gpt-4o-transcribe"


async def test_rejects_unknown_engine(session: AsyncSession) -> None:
    with pytest.raises(ValueError, match="transcription_engine"):
        await save_ai_config(session, {"transcription_engine": "magic"})


async def test_rejects_unknown_provider(session: AsyncSession) -> None:
    with pytest.raises(ValueError, match=r"(?i)provider"):
        await save_ai_config(
            session,
            {
                "transcription_engine": "cloud",
                "provider": "no-such-lab",
                "transcription_model": "x",
                "api_key": "sk-x",
            },
        )


async def test_rejects_unavailable_provider(session: AsyncSession) -> None:
    # anthropic is listed for visibility but can't transcribe via api.
    with pytest.raises(ValueError, match=r"(?i)not available"):
        await save_ai_config(
            session,
            {
                "transcription_engine": "cloud",
                "provider": "anthropic",
                "transcription_model": "claude",
                "api_key": "sk-x",
            },
        )


async def test_rejects_model_not_in_catalog(session: AsyncSession) -> None:
    with pytest.raises(ValueError, match=r"(?i)model"):
        await save_ai_config(
            session,
            {
                "transcription_engine": "cloud",
                "provider": "openai",
                "transcription_model": "not-a-real-model",
                "api_key": "sk-x",
            },
        )


async def test_self_hosted_allows_localhost(session: AsyncSession) -> None:
    # the open-source/self-hosted option's whole point is a local server,
    # so the loopback/private block is lifted for it (and custom).
    await save_ai_config(
        session,
        {
            "transcription_engine": "cloud",
            "provider": "oss",
            "transcription_model": "whisper-large-v3",
            "api_base_url": "http://localhost:9000/v1",
        },
    )
    config = await load_ai_config(session)
    assert config.provider == "oss"
    assert config.api_base_url == "http://localhost:9000/v1"
    # oss may run keyless, so cloud is enabled without an api key
    assert config.cloud_transcription_enabled is True


async def test_legacy_config_without_provider_is_custom(
    session: AsyncSession,
) -> None:
    # a config saved before providers existed (no provider field) is
    # treated as a custom OpenAI-compatible endpoint and keeps working.
    await save_ai_config(
        session,
        {
            "transcription_engine": "cloud",
            "api_base_url": "https://api.openai.com/v1",
            "api_key": "sk-legacy",
            "transcription_model": "whisper-1",
        },
    )
    config = await load_ai_config(session)
    assert config.provider == "custom"
    assert config.cloud_transcription_enabled is True


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


def test_validate_endpoint_allow_local_permits_loopback() -> None:
    # self-hosted/custom providers opt into local targets...
    validate_endpoint("http://localhost:9000/v1", allow_local=True)
    validate_endpoint("http://192.168.1.10:9000/v1", allow_local=True)


def test_validate_endpoint_allow_local_still_rejects_bad_scheme() -> None:
    # ...but the http(s) structural check always applies.
    with pytest.raises(ValueError):
        validate_endpoint("ftp://localhost/v1", allow_local=True)
    with pytest.raises(ValueError):
        validate_endpoint("not-a-url", allow_local=True)
