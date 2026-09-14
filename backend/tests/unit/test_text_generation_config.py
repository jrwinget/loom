"""unit tests for runtime text-generation configuration."""

from collections.abc import AsyncIterator
from pathlib import Path

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from loom.config import Settings
from loom.models.app_setting import AppSetting
from loom.models.base import Base
from loom.services import ai_config as ai_config_module
from loom.services import secret_box as secret_box_module
from loom.services.ai_config import (
    load_ai_config,
    load_text_gen_config,
    save_ai_config,
    save_text_gen_config,
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


@pytest.fixture
def lite_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = Settings(deployment_profile="lite")
    monkeypatch.setattr(ai_config_module, "get_settings", lambda: settings)


@pytest.fixture
def isolated_secret_key(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    settings = Settings(data_dir=tmp_path)
    monkeypatch.setattr(secret_box_module, "get_settings", lambda: settings)


async def test_defaults_when_unset(session: AsyncSession) -> None:
    config = await load_text_gen_config(session)
    assert config.enabled is False
    assert config.provider == ""
    assert config.usable is False
    assert config.provider_available is True
    assert config.key_decryptable is True


async def test_custom_round_trip(
    session: AsyncSession, isolated_secret_key: None
) -> None:
    await save_text_gen_config(
        session,
        {
            "enabled": True,
            "provider": "custom",
            "api_base_url": "https://my-llm.example.com/v1",
            "api_key": "sk-text-gen",
            "model": "my-model",
        },
    )
    config = await load_text_gen_config(session)
    assert config.provider == "custom"
    assert config.api_base_url == "https://my-llm.example.com/v1"
    assert config.api_key == "sk-text-gen"
    assert config.usable is True


@pytest.mark.usefixtures("lite_settings")
async def test_oss_provider_is_keyless_and_may_target_loopback(
    session: AsyncSession,
) -> None:
    await save_text_gen_config(
        session,
        {
            "enabled": True,
            "provider": "oss",
            "api_base_url": "http://127.0.0.1:11434/v1",
            "model": "gpt-oss-20b",
        },
    )
    config = await load_text_gen_config(session)
    assert config.usable is True  # no api key needed


async def test_disabled_config_is_never_usable_even_if_fully_configured(
    session: AsyncSession, isolated_secret_key: None
) -> None:
    await save_text_gen_config(
        session,
        {
            "enabled": False,
            "provider": "custom",
            "api_base_url": "https://my-llm.example.com/v1",
            "api_key": "sk-text-gen",
            "model": "my-model",
        },
    )
    config = await load_text_gen_config(session)
    assert config.usable is False


async def test_rejects_unknown_provider(session: AsyncSession) -> None:
    with pytest.raises(
        ValueError, match=r"(?i)unknown text-generation provider"
    ):
        await save_text_gen_config(
            session,
            {
                "enabled": True,
                "provider": "openai",
                "api_base_url": "https://api.openai.com/v1",
                "model": "gpt-4o",
            },
        )


async def test_partial_update_preserves_key(
    session: AsyncSession, isolated_secret_key: None
) -> None:
    await save_text_gen_config(
        session,
        {
            "enabled": True,
            "provider": "custom",
            "api_base_url": "https://my-llm.example.com/v1",
            "api_key": "sk-keep",
            "model": "my-model",
        },
    )
    await save_text_gen_config(session, {"model": "a-different-model"})
    config = await load_text_gen_config(session)
    assert config.api_key == "sk-keep"
    assert config.model == "a-different-model"


async def test_api_key_is_encrypted_at_rest(
    session: AsyncSession, isolated_secret_key: None
) -> None:
    await save_text_gen_config(
        session,
        {
            "enabled": True,
            "provider": "custom",
            "api_base_url": "https://my-llm.example.com/v1",
            "api_key": "sk-super-secret",
            "model": "my-model",
        },
    )
    row = await session.scalar(
        select(AppSetting).where(AppSetting.key == "ai_text_generation")
    )
    assert row is not None
    assert "api_key" not in row.value
    stored = row.value["api_key_enc"]
    assert isinstance(stored, dict)
    assert "sk-super-secret" not in str(stored)


async def test_transcription_and_text_generation_configs_are_independent(
    session: AsyncSession, isolated_secret_key: None
) -> None:
    # opting a self-hosted endpoint in for transcription must not
    # silently authorize text-generation egress to the same host.
    await save_ai_config(
        session,
        {
            "transcription_engine": "cloud",
            "provider": "custom",
            "api_key": "sk-transcription",
            "api_base_url": "https://transcribe.example.com/v1",
            "transcription_model": "whisper-1",
        },
    )
    text_gen = await load_text_gen_config(session)
    assert text_gen.enabled is False
    assert text_gen.usable is False

    transcription = await load_ai_config(session)
    assert transcription.cloud_transcription_enabled is True
