"""unit tests for runtime AI engine configuration."""

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
from loom.models.audit import AuditLogEntry
from loom.models.base import Base
from loom.services import ai_config as ai_config_module
from loom.services import secret_box as secret_box_module
from loom.services.ai_config import (
    assert_resolved_host_safe,
    load_ai_config,
    reconcile_retired_provider,
    save_ai_config,
    validate_endpoint,
)


@pytest_asyncio.fixture
async def session() -> AsyncIterator[AsyncSession]:
    engine = create_async_engine("sqlite+aiosqlite://")
    async with engine.begin() as conn:
        await conn.run_sync(
            Base.metadata.create_all,
            tables=[AppSetting.__table__, AuditLogEntry.__table__],
        )
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as s:
        yield s
    await engine.dispose()


@pytest.fixture
def lite_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    """point every ``get_settings()`` call used by this module at a lite
    -profile instance, so allow_local's loopback allowance applies."""
    settings = Settings(deployment_profile="lite")
    monkeypatch.setattr(ai_config_module, "get_settings", lambda: settings)


@pytest.fixture
def isolated_secret_key(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """give the encryption key a private, per-test file location so
    tests don't share (or race on) a real per-install key file."""
    settings = Settings(data_dir=tmp_path)
    monkeypatch.setattr(secret_box_module, "get_settings", lambda: settings)


async def test_defaults_when_unset(session: AsyncSession) -> None:
    config = await load_ai_config(session)
    assert config.transcription_engine == "local"
    assert config.provider == ""
    assert config.cloud_transcription_enabled is False
    assert config.provider_available is True
    assert config.key_decryptable is True


@pytest.mark.usefixtures("lite_settings")
async def test_self_hosted_round_trip(
    session: AsyncSession, isolated_secret_key: None
) -> None:
    await save_ai_config(
        session,
        {
            "transcription_engine": "cloud",
            "provider": "oss",
            "transcription_model": "whisper-large-v3",
            "api_base_url": "http://127.0.0.1:9000/v1",
        },
    )
    config = await load_ai_config(session)
    assert config.provider == "oss"
    assert config.api_base_url == "http://127.0.0.1:9000/v1"
    # oss may run keyless, so cloud is enabled without an api key
    assert config.cloud_transcription_enabled is True


async def test_partial_update_preserves_key(
    session: AsyncSession, isolated_secret_key: None
) -> None:
    await save_ai_config(
        session,
        {
            "transcription_engine": "cloud",
            "provider": "custom",
            "api_key": "sk-keep",
            "api_base_url": "https://transcribe.example.com/v1",
            "transcription_model": "whisper-1",
        },
    )
    # a later update that omits api_key must not wipe it
    await save_ai_config(session, {"transcription_model": "whisper-large-v3"})
    config = await load_ai_config(session)
    assert config.api_key == "sk-keep"
    assert config.transcription_model == "whisper-large-v3"


async def test_rejects_unknown_engine(session: AsyncSession) -> None:
    with pytest.raises(ValueError, match="transcription_engine"):
        await save_ai_config(session, {"transcription_engine": "magic"})


async def test_rejects_unknown_provider(session: AsyncSession) -> None:
    with pytest.raises(ValueError, match=r"(?i)unknown ai provider"):
        await save_ai_config(
            session,
            {
                "transcription_engine": "cloud",
                "provider": "no-such-lab",
                "transcription_model": "x",
                "api_key": "sk-x",
            },
        )


@pytest.mark.parametrize("retired", ["openai", "google", "anthropic"])
async def test_rejects_retired_frontier_provider(
    session: AsyncSession, retired: str
) -> None:
    with pytest.raises(ValueError, match=r"(?i)unknown ai provider"):
        await save_ai_config(
            session,
            {
                "transcription_engine": "cloud",
                "provider": retired,
                "transcription_model": "x",
                "api_key": "sk-x",
            },
        )


async def test_rejects_model_not_in_catalog(session: AsyncSession) -> None:
    with pytest.raises(ValueError, match=r"(?i)model"):
        await save_ai_config(
            session,
            {
                "transcription_engine": "cloud",
                "provider": "oss",
                "transcription_model": "not-a-real-model",
            },
        )


async def test_legacy_config_without_provider_is_custom(
    session: AsyncSession, isolated_secret_key: None
) -> None:
    # a config saved before providers existed (no provider field) is
    # treated as a custom OpenAI-compatible endpoint and keeps working.
    await save_ai_config(
        session,
        {
            "transcription_engine": "cloud",
            "api_base_url": "https://api.example.com/v1",
            "api_key": "sk-legacy",
            "transcription_model": "whisper-1",
        },
    )
    config = await load_ai_config(session)
    assert config.provider == "custom"
    assert config.cloud_transcription_enabled is True


# -- encryption at rest -------------------------------------------------


async def test_api_key_is_encrypted_at_rest(
    session: AsyncSession, isolated_secret_key: None
) -> None:
    await save_ai_config(
        session,
        {
            "transcription_engine": "cloud",
            "provider": "custom",
            "api_base_url": "https://api.example.com/v1",
            "api_key": "sk-super-secret",
            "transcription_model": "whisper-1",
        },
    )
    row = await session.scalar(select(AppSetting).where(AppSetting.key == "ai"))
    assert row is not None
    assert "api_key" not in row.value
    stored = row.value["api_key_enc"]
    assert isinstance(stored, dict)
    assert stored["v"] == 1
    assert "sk-super-secret" not in str(stored)

    config = await load_ai_config(session)
    assert config.api_key == "sk-super-secret"
    assert config.key_decryptable is True


async def test_legacy_plaintext_key_is_read_and_then_reencrypted(
    session: AsyncSession, isolated_secret_key: None
) -> None:
    session.add(
        AppSetting(
            key="ai",
            value={
                "transcription_engine": "cloud",
                "provider": "custom",
                "api_base_url": "https://api.example.com/v1",
                "api_key": "sk-plain-legacy",
                "transcription_model": "whisper-1",
                "whisper_model": "base",
            },
        )
    )
    await session.flush()

    config = await load_ai_config(session)
    assert config.api_key == "sk-plain-legacy"
    assert config.key_decryptable is True

    # any save transparently upgrades the stored value to an encrypted blob
    await save_ai_config(session, {"whisper_model": "small"})
    row = await session.scalar(select(AppSetting).where(AppSetting.key == "ai"))
    assert row is not None
    assert "api_key" not in row.value
    assert isinstance(row.value["api_key_enc"], dict)


async def test_key_undecryptable_with_a_different_key_fails_closed(
    session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings_a = Settings(ai_secret_key="key-a")
    monkeypatch.setattr(secret_box_module, "get_settings", lambda: settings_a)
    await save_ai_config(
        session,
        {
            "transcription_engine": "cloud",
            "provider": "custom",
            "api_base_url": "https://api.example.com/v1",
            "api_key": "sk-only-key-a-can-read-this",
            "transcription_model": "whisper-1",
        },
    )

    settings_b = Settings(ai_secret_key="key-b")
    monkeypatch.setattr(secret_box_module, "get_settings", lambda: settings_b)
    config = await load_ai_config(session)
    assert config.api_key == ""
    assert config.key_decryptable is False
    # an undecryptable key must not silently be treated as "no key
    # configured, so keyless self-hosted is fine" — cloud must be off.
    assert config.cloud_transcription_enabled is False


# -- provider retirement / fail-closed behavior -------------------------


async def test_provider_unavailable_fails_closed_without_reconciliation(
    session: AsyncSession,
) -> None:
    # simulate a stale row written before frontier providers were
    # removed, without ever running the startup reconciliation.
    session.add(
        AppSetting(
            key="ai",
            value={
                "transcription_engine": "cloud",
                "provider": "openai",
                "api_base_url": "https://api.openai.com/v1",
                "api_key": "sk-stale",
                "transcription_model": "gpt-4o-transcribe",
                "whisper_model": "base",
            },
        )
    )
    await session.flush()

    config = await load_ai_config(session)
    assert config.provider_available is False
    assert config.cloud_transcription_enabled is False


async def test_reconcile_retired_provider_clears_stale_config(
    session: AsyncSession,
) -> None:
    session.add(
        AppSetting(
            key="ai",
            value={
                "transcription_engine": "cloud",
                "provider": "openai",
                "api_base_url": "https://api.openai.com/v1",
                "api_key": "sk-stale",
                "transcription_model": "gpt-4o-transcribe",
                "whisper_model": "base",
            },
        )
    )
    await session.flush()

    changed = await reconcile_retired_provider(session)
    assert changed is True

    config = await load_ai_config(session)
    assert config.transcription_engine == "local"
    assert config.provider == ""
    assert config.api_key == ""
    assert config.cloud_transcription_enabled is False

    entries = (
        (
            await session.execute(
                select(AuditLogEntry).where(
                    AuditLogEntry.action == "ai_provider_retired"
                )
            )
        )
        .scalars()
        .all()
    )
    assert len(entries) == 1
    assert entries[0].detail["previous_provider"] == "openai"
    assert entries[0].detail["key_cleared"] is True


async def test_reconcile_retired_provider_is_a_noop_when_not_retired(
    session: AsyncSession, isolated_secret_key: None
) -> None:
    await save_ai_config(
        session,
        {
            "transcription_engine": "cloud",
            "provider": "oss",
            "transcription_model": "whisper-large-v3",
        },
    )
    assert await reconcile_retired_provider(session) is False


# -- endpoint validation / ssrf hardening -------------------------------


@pytest.mark.parametrize(
    "bad",
    [
        "http://localhost/v1",
        "http://127.0.0.1/v1",
        "https://10.0.0.5/v1",
        "ftp://example.com/v1",
        "not-a-url",
        # always-banned regardless of allow_local
        "http://169.254.169.254/latest/meta-data",  # cloud metadata
        "http://[::ffff:127.0.0.1]/v1",  # ipv4-mapped loopback
        "http://0.0.0.1/v1",
        "http://100.64.0.5/v1",  # cgnat
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


@pytest.mark.usefixtures("lite_settings")
def test_validate_endpoint_allow_local_permits_loopback_on_lite() -> None:
    validate_endpoint("http://localhost:9000/v1", allow_local=True)
    validate_endpoint("http://127.0.0.1:9000/v1", allow_local=True)


def test_validate_endpoint_allow_local_rejects_loopback_on_server() -> None:
    # the default profile in tests is "server"; a server deployment has
    # no legitimate reason to aim the backend at its own loopback.
    with pytest.raises(ValueError, match=r"(?i)localhost"):
        validate_endpoint("http://localhost:9000/v1", allow_local=True)


def test_validate_endpoint_allow_local_permits_lan_over_https() -> None:
    # a private/lan self-hosted target is fine on any profile, but must
    # use https now.
    validate_endpoint("https://192.168.1.10:9000/v1", allow_local=True)


def test_validate_endpoint_allow_local_requires_https_for_lan() -> None:
    with pytest.raises(ValueError, match=r"(?i)https"):
        validate_endpoint("http://192.168.1.10:9000/v1", allow_local=True)


@pytest.mark.parametrize(
    "always_banned",
    [
        "http://169.254.169.254/v1",
        "http://0.0.0.1/v1",
        "http://100.64.0.5/v1",
    ],
)
@pytest.mark.usefixtures("lite_settings")
def test_validate_endpoint_allow_local_still_rejects_always_banned(
    always_banned: str,
) -> None:
    with pytest.raises(ValueError):
        validate_endpoint(always_banned, allow_local=True)


@pytest.mark.usefixtures("lite_settings")
def test_validate_endpoint_allow_local_permits_mapped_loopback() -> None:
    # an ipv4-mapped ipv6 loopback address is just another encoding of
    # 127.0.0.1 — it's checked against the same loopback rule, not
    # treated as categorically banned.
    validate_endpoint("http://[::ffff:127.0.0.1]:9000/v1", allow_local=True)


def test_validate_endpoint_allow_local_still_rejects_bad_scheme() -> None:
    with pytest.raises(ValueError):
        validate_endpoint("ftp://localhost/v1", allow_local=True)
    with pytest.raises(ValueError):
        validate_endpoint("not-a-url", allow_local=True)


# -- request-time dns-rebinding check -----------------------------------


def test_assert_resolved_host_safe_accepts_public_ip(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        ai_config_module.socket,
        "getaddrinfo",
        lambda *a, **k: [(None, None, None, None, ("8.8.8.8", 0))],
    )
    assert_resolved_host_safe(
        "https://transcribe.example.com/v1", allow_local=False
    )


def test_assert_resolved_host_safe_rejects_dns_rebind_to_metadata(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # a hostname that looked fine at save time but now resolves to the
    # cloud metadata endpoint must be caught here even though it would
    # pass validate_endpoint()'s no-dns structural check.
    monkeypatch.setattr(
        ai_config_module.socket,
        "getaddrinfo",
        lambda *a, **k: [(None, None, None, None, ("169.254.169.254", 0))],
    )
    with pytest.raises(ValueError):
        assert_resolved_host_safe(
            "https://transcribe.example.com/v1", allow_local=True
        )


def test_assert_resolved_host_safe_rejects_unresolvable_host(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _raise(*_a: object, **_k: object) -> None:
        raise OSError("no such host")

    monkeypatch.setattr(ai_config_module.socket, "getaddrinfo", _raise)
    with pytest.raises(ValueError, match=r"(?i)did not resolve"):
        assert_resolved_host_safe(
            "https://nowhere.invalid/v1", allow_local=False
        )


# -- whisper model (unchanged local-engine config) -----------------------


async def test_whisper_model_round_trip(session: AsyncSession) -> None:
    await save_ai_config(session, {"whisper_model": "small"})
    config = await load_ai_config(session)
    assert config.whisper_model == "small"


async def test_whisper_model_rejects_unknown(session: AsyncSession) -> None:
    # local transcription resolves through the pinned registry, so a
    # name outside the catalog could never load
    with pytest.raises(ValueError, match="whisper_model"):
        await save_ai_config(session, {"whisper_model": "gigantic"})
