"""runtime AI engine configuration (key ``"ai"`` in app_settings).

local on-device engines are the default. a user may opt in to a cloud
provider by supplying an OpenAI-compatible base url, api key, and model;
when they do, evidence is sent off the machine, so the choice is
explicit, persisted per-install, and recorded in chain of custody at
inference time.
"""

from __future__ import annotations

import ipaddress
from dataclasses import dataclass, replace
from typing import Any
from urllib.parse import urlparse

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from loom.models.app_setting import AppSetting
from loom.services.ai_providers import (
    get_provider,
    requires_api_key,
    validate_selection,
)

_AI_KEY = "ai"
_ALLOWED_ENGINES = ("local", "cloud")
_DEFAULT_BASE_URL = "https://api.openai.com/v1"
_DEFAULT_MODEL = "whisper-1"
_EDITABLE_FIELDS = (
    "transcription_engine",
    "provider",
    "api_base_url",
    "api_key",
    "transcription_model",
)


@dataclass(frozen=True)
class AiConfig:
    transcription_engine: str = "local"
    # which catalog provider the cloud config targets ("" for configs
    # saved before providers existed; treated as a custom endpoint).
    provider: str = ""
    api_base_url: str = _DEFAULT_BASE_URL
    api_key: str = ""
    transcription_model: str = _DEFAULT_MODEL

    @property
    def cloud_transcription_enabled(self) -> bool:
        if self.transcription_engine != "cloud" or not self.api_base_url:
            return False
        # self-hosted/open-source providers may run keyless; hosted
        # providers need a key before we'll send audio off the machine.
        if requires_api_key(self.provider):
            return bool(self.api_key)
        return True


def validate_endpoint(url: str, *, allow_local: bool = False) -> None:
    """reject obviously-internal or non-http(s) cloud endpoints.

    a structural (no-DNS) check so it stays offline-safe: the BYO
    provider is user-supplied, so this only blocks accidental or
    malicious targeting of loopback/private hosts.

    ``allow_local`` is set for the self-hosted/custom providers, whose
    whole point is pointing at a local or LAN inference server; hosted
    providers keep the loopback/private block. the http(s) structural
    check always applies, and this setting is admin-only either way.
    """
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        raise ValueError("ai endpoint must be an absolute http(s) url")
    if allow_local:
        return
    host = parsed.hostname
    if host in ("localhost",) or host.endswith(".localhost"):
        raise ValueError("ai endpoint may not target localhost")
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        return  # a hostname; structural check passes
    if ip.is_loopback or ip.is_private or ip.is_link_local:
        raise ValueError("ai endpoint may not target a private address")


async def load_ai_config(session: AsyncSession) -> AiConfig:
    row = await session.scalar(
        select(AppSetting).where(AppSetting.key == _AI_KEY)
    )
    if row is None or not isinstance(row.value, dict):
        return AiConfig()
    data = row.value
    return AiConfig(
        transcription_engine=str(data.get("transcription_engine", "local")),
        provider=str(data.get("provider", "")),
        api_base_url=str(data.get("api_base_url", _DEFAULT_BASE_URL)),
        api_key=str(data.get("api_key", "")),
        transcription_model=str(
            data.get("transcription_model", _DEFAULT_MODEL)
        ),
    )


async def save_ai_config(
    session: AsyncSession, patch: dict[str, Any]
) -> AiConfig:
    """merge ``patch`` over the stored config and persist it.

    a None field is left unchanged (so the api key isn't wiped by a
    form that doesn't re-send it); pass an explicit "" to clear.
    """
    current = await load_ai_config(session)
    changes = {
        field: patch[field]
        for field in _EDITABLE_FIELDS
        if patch.get(field) is not None
    }
    updated = replace(current, **changes)

    if updated.transcription_engine not in _ALLOWED_ENGINES:
        raise ValueError(
            f"transcription_engine must be one of {_ALLOWED_ENGINES}"
        )
    if updated.transcription_engine == "cloud":
        # an empty provider (a pre-providers config) is treated as a
        # custom OpenAI-compatible endpoint so it keeps working.
        provider_id = updated.provider or "custom"
        validate_selection(provider_id, updated.transcription_model)
        provider = get_provider(provider_id)
        assert provider is not None  # validate_selection guarantees this
        # hosted providers use the catalog base url; self-hosted/custom
        # keep the user's and may target a local server.
        base_url = (
            updated.api_base_url
            if provider.base_url_editable
            else provider.base_url
        )
        validate_endpoint(base_url, allow_local=provider.base_url_editable)
        updated = replace(updated, provider=provider_id, api_base_url=base_url)

    value = {
        "transcription_engine": updated.transcription_engine,
        "provider": updated.provider,
        "api_base_url": updated.api_base_url,
        "api_key": updated.api_key,
        "transcription_model": updated.transcription_model,
    }
    row = await session.scalar(
        select(AppSetting).where(AppSetting.key == _AI_KEY)
    )
    if row is None:
        session.add(AppSetting(key=_AI_KEY, value=value))
    else:
        row.value = value
    await session.flush()
    return updated
