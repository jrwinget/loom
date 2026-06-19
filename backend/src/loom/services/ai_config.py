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

_AI_KEY = "ai"
_ALLOWED_ENGINES = ("local", "cloud")
_DEFAULT_BASE_URL = "https://api.openai.com/v1"
_DEFAULT_MODEL = "whisper-1"
_EDITABLE_FIELDS = (
    "transcription_engine",
    "api_base_url",
    "api_key",
    "transcription_model",
)


@dataclass(frozen=True)
class AiConfig:
    transcription_engine: str = "local"
    api_base_url: str = _DEFAULT_BASE_URL
    api_key: str = ""
    transcription_model: str = _DEFAULT_MODEL

    @property
    def cloud_transcription_enabled(self) -> bool:
        return (
            self.transcription_engine == "cloud"
            and bool(self.api_key)
            and bool(self.api_base_url)
        )


def validate_endpoint(url: str) -> None:
    """reject obviously-internal or non-http(s) cloud endpoints.

    a structural (no-DNS) check so it stays offline-safe: the BYO
    provider is user-supplied, so this only blocks accidental or
    malicious targeting of loopback/private hosts.
    """
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        raise ValueError("ai endpoint must be an absolute http(s) url")
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
        validate_endpoint(updated.api_base_url)

    value = {
        "transcription_engine": updated.transcription_engine,
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
