"""runtime AI engine configuration (key ``"ai"`` in app_settings).

local on-device engines are the default. a user may opt in to a cloud
provider by supplying an OpenAI-compatible base url, api key, and model;
when they do, evidence is sent off the machine, so the choice is
explicit, persisted per-install, and recorded in chain of custody at
inference time.
"""

from __future__ import annotations

import ipaddress
import socket
from dataclasses import dataclass, replace
from typing import Any
from urllib.parse import urlparse

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from loom.config import get_settings
from loom.models.app_setting import AppSetting
from loom.models.audit import AuditLogEntry
from loom.services.ai_providers import (
    RETIRED_PROVIDER_IDS,
    get_provider,
    requires_api_key,
    validate_selection,
)
from loom.services.model_registry import WHISPER_MODELS
from loom.services.secret_box import (
    SecretUnavailableError,
    decrypt_secret,
    encrypt_secret,
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
    "whisper_model",
)

IPAddress = ipaddress.IPv4Address | ipaddress.IPv6Address

# ranges the stdlib's is_private/is_link_local don't fully cover but that
# are never a legitimate ai endpoint target: 0.0.0.0/8 (beyond the single
# is_unspecified address) and the cgnat shared address space.
_ALWAYS_BANNED_NETWORKS = tuple(
    ipaddress.ip_network(cidr) for cidr in ("0.0.0.0/8", "100.64.0.0/10")
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
    # which pinned whisper model local transcription loads; must be
    # downloaded via the model manager before a transcribe succeeds
    whisper_model: str = "base"
    # false only when a stored api key exists but can't be decrypted
    # with the currently-available key (rotated/lost key, corrupt data).
    key_decryptable: bool = True

    @property
    def provider_available(self) -> bool:
        """false for a provider id that no longer exists in the catalog
        (removed, or retired) — an empty provider (pre-catalog config,
        treated as "custom") is always available."""
        return not self.provider or get_provider(self.provider) is not None

    @property
    def cloud_transcription_enabled(self) -> bool:
        if self.transcription_engine != "cloud" or not self.api_base_url:
            return False
        # a provider withdrawn from the catalog must not keep silently
        # calling its old endpoint just because a config row still
        # names it — this holds even if reconcile_retired_provider()
        # never ran (e.g. a restored backup, or an install that
        # predates it).
        if not self.provider_available:
            return False
        if not self.key_decryptable:
            return False
        # self-hosted/open-source providers may run keyless; hosted
        # providers need a key before we'll send audio off the machine.
        if requires_api_key(self.provider):
            return bool(self.api_key)
        return True


def _is_always_banned(ip: IPAddress) -> bool:
    """networks that are never a legitimate ai endpoint target, even for
    a self-hosted/lan config: link-local (this covers cloud metadata
    services like 169.254.169.254), multicast, reserved, unspecified,
    and cgnat. checked against the ipv4-mapped address when applicable
    so ``::ffff:127.0.0.1``-style addresses can't slip past as "just an
    ipv6 hostname"."""
    mapped = getattr(ip, "ipv4_mapped", None)
    check = mapped or ip
    if (
        check.is_link_local
        or check.is_multicast
        or check.is_reserved
        or check.is_unspecified
    ):
        return True
    return any(check in net for net in _ALWAYS_BANNED_NETWORKS)


def _check_ip(
    ip: IPAddress, *, allow_local: bool, allow_loopback: bool
) -> None:
    """raise if ``ip`` isn't a safe target.

    ``allow_local`` permits private/lan addresses (the self-hosted/custom
    point). ``allow_loopback`` separately permits loopback — only true on
    the lite profile, where the self-hosted server plausibly runs
    alongside the app on the same machine; a multi-container server
    deployment's "loopback" is the api container itself, not a real
    inference target, so a server install never gets this even when it
    requested a self-hosted provider.
    """
    if _is_always_banned(ip):
        raise ValueError(
            "ai endpoint may not target a reserved or link-local address"
        )
    mapped = getattr(ip, "ipv4_mapped", None)
    check = mapped or ip
    if check.is_loopback:
        if not allow_loopback:
            raise ValueError("ai endpoint may not target localhost")
        return
    if check.is_private:
        if not allow_local:
            raise ValueError("ai endpoint may not target a private address")
        return


def _is_loopback_host(host: str, literal_ip: IPAddress | None) -> bool:
    if host in ("localhost",) or host.endswith(".localhost"):
        return True
    if literal_ip is None:
        return False
    mapped = getattr(literal_ip, "ipv4_mapped", None)
    return bool((mapped or literal_ip).is_loopback)


def validate_endpoint(url: str, *, allow_local: bool = False) -> None:
    """reject obviously-internal, non-http(s), or otherwise unsafe
    cloud/self-hosted endpoints.

    a structural (no-DNS) check on the literal url so it stays
    offline-safe and cheap to run on every request, not just at save
    time — call it again immediately before dispatching a request, since
    a config row can be written by a path other than ``save_ai_config``
    (e.g. a direct db edit) and would otherwise never be checked. for a
    hostname (not a literal ip), pair this with
    :func:`assert_resolved_host_safe` at request time to also catch a
    hostname that resolves somewhere unsafe (dns rebinding) — this
    function alone cannot see that without a dns lookup.

    ``allow_local`` is requested by the self-hosted/custom providers,
    whose whole point is pointing at a local or lan inference server.
    loopback specifically is only permitted on the ``lite`` deployment
    profile (see :func:`_check_ip`); a non-loopback private/lan address
    is allowed on both profiles, but must use https. link-local
    /multicast/reserved/cgnat ranges are rejected unconditionally either
    way.
    """
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        raise ValueError("ai endpoint must be an absolute http(s) url")
    host = parsed.hostname
    allow_loopback = allow_local and get_settings().is_lite

    try:
        literal_ip: IPAddress | None = ipaddress.ip_address(host)
    except ValueError:
        literal_ip = None
    is_loopback_host = _is_loopback_host(host, literal_ip)

    if literal_ip is not None:
        _check_ip(
            literal_ip, allow_local=allow_local, allow_loopback=allow_loopback
        )
    elif is_loopback_host and not allow_loopback:
        raise ValueError("ai endpoint may not target localhost")

    if not allow_local:
        return  # a hosted-catalog endpoint; nothing left to check
    if not is_loopback_host and parsed.scheme != "https":
        raise ValueError(
            "a non-loopback ai endpoint must use https "
            "(only 127.0.0.1/localhost may use plain http)"
        )


def assert_resolved_host_safe(url: str, *, allow_local: bool) -> None:
    """re-validate at request time by resolving the hostname and
    checking the actual address(es) it resolves to right now.

    closes the dns-rebinding gap: a hostname can pass
    :func:`validate_endpoint`'s structural check at save time and later
    resolve to a banned/internal address at request time. call this
    immediately before making the actual request, in addition to
    :func:`validate_endpoint`.
    """
    parsed = urlparse(url)
    host = parsed.hostname
    if not host:
        raise ValueError("ai endpoint must be an absolute http(s) url")
    allow_loopback = allow_local and get_settings().is_lite

    if _is_loopback_host(host, None):
        if not allow_loopback:
            raise ValueError("ai endpoint may not target localhost")
        return
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        ip = None
    if ip is not None:
        _check_ip(ip, allow_local=allow_local, allow_loopback=allow_loopback)
        return
    try:
        infos = socket.getaddrinfo(host, None)
    except OSError as exc:
        raise ValueError(
            f"ai endpoint hostname did not resolve: {host!r}"
        ) from exc
    for info in infos:
        _check_ip(
            ipaddress.ip_address(info[4][0]),
            allow_local=allow_local,
            allow_loopback=allow_loopback,
        )


async def load_ai_config(session: AsyncSession) -> AiConfig:
    row = await session.scalar(
        select(AppSetting).where(AppSetting.key == _AI_KEY)
    )
    if row is None or not isinstance(row.value, dict):
        return AiConfig()
    data = row.value
    stored_key = data.get("api_key_enc", data.get("api_key", ""))
    try:
        api_key = decrypt_secret(stored_key)
        key_decryptable = True
    except SecretUnavailableError:
        api_key = ""
        key_decryptable = False
    return AiConfig(
        transcription_engine=str(data.get("transcription_engine", "local")),
        provider=str(data.get("provider", "")),
        api_base_url=str(data.get("api_base_url", _DEFAULT_BASE_URL)),
        api_key=api_key,
        transcription_model=str(
            data.get("transcription_model", _DEFAULT_MODEL)
        ),
        whisper_model=str(data.get("whisper_model", "base")),
        key_decryptable=key_decryptable,
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
    if updated.whisper_model not in WHISPER_MODELS:
        known = ", ".join(sorted(WHISPER_MODELS))
        raise ValueError(f"whisper_model must be one of: {known}")
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
        updated = replace(
            updated,
            provider=provider_id,
            api_base_url=base_url,
            key_decryptable=True,
        )

    value = {
        "transcription_engine": updated.transcription_engine,
        "provider": updated.provider,
        "api_base_url": updated.api_base_url,
        "api_key_enc": encrypt_secret(updated.api_key),
        "transcription_model": updated.transcription_model,
        "whisper_model": updated.whisper_model,
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


async def reconcile_retired_provider(session: AsyncSession) -> bool:
    """clear a stale cloud-transcription config left pointing at a
    frontier provider that has since been removed from the catalog.

    intended to run once at application startup. safe to call
    repeatedly (a no-op once cleared). not required for safety on its
    own — :attr:`AiConfig.cloud_transcription_enabled` independently
    refuses a provider missing from the catalog even if this never ran
    (e.g. a restored backup) — this exists to stop a dead api key from
    lingering in the database and to leave an audit trail of the
    retirement.
    """
    row = await session.scalar(
        select(AppSetting).where(AppSetting.key == _AI_KEY)
    )
    if row is None or not isinstance(row.value, dict):
        return False
    previous_provider = row.value.get("provider")
    if previous_provider not in RETIRED_PROVIDER_IDS:
        return False
    row.value = {
        **row.value,
        "transcription_engine": "local",
        "provider": "",
        "api_base_url": _DEFAULT_BASE_URL,
        "api_key": "",
        "api_key_enc": "",
    }
    session.add(
        AuditLogEntry(
            actor_id=None,
            action="ai_provider_retired",
            resource_type="app_setting",
            resource_id=row.id,
            detail={
                "previous_provider": previous_provider,
                "key_cleared": True,
            },
        )
    )
    await session.flush()
    return True
