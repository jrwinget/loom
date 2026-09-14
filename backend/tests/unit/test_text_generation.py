"""unit tests for self-hosted/custom text generation (no real network)."""

import json
from typing import Any, ClassVar

import pytest

from loom.services import text_generation


class _FakeResponse:
    def __init__(self, payload: dict[str, Any]) -> None:
        self._body = json.dumps(payload).encode("utf-8")

    def raise_for_status(self) -> None:
        return None

    async def aiter_bytes(self) -> Any:
        yield self._body


class _FakeStreamCtx:
    def __init__(self, resp: _FakeResponse) -> None:
        self._resp = resp

    async def __aenter__(self) -> _FakeResponse:
        return self._resp

    async def __aexit__(self, *_args: object) -> bool:
        return False


class _FakeClient:
    last_kwargs: ClassVar[dict[str, Any]] = {}
    last_client_kwargs: ClassVar[dict[str, Any]] = {}

    def __init__(self, payload: dict[str, Any]) -> None:
        self._payload = payload

    async def __aenter__(self) -> "_FakeClient":
        return self

    async def __aexit__(self, *_args: object) -> bool:
        return False

    def stream(self, method: str, url: str, **kwargs: Any) -> _FakeStreamCtx:
        _FakeClient.last_kwargs = {"method": method, "url": url, **kwargs}
        return _FakeStreamCtx(_FakeResponse(self._payload))


@pytest.fixture(autouse=True)
def _no_real_dns_lookup(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        text_generation, "assert_resolved_host_safe", lambda *a, **k: None
    )


def _patch_client(
    monkeypatch: pytest.MonkeyPatch, payload: dict[str, Any]
) -> None:
    def _make_client(*_a: object, **kwargs: object) -> _FakeClient:
        _FakeClient.last_client_kwargs = dict(kwargs)
        return _FakeClient(payload)

    monkeypatch.setattr(text_generation.httpx, "AsyncClient", _make_client)


async def test_returns_the_first_choice_message(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_client(
        monkeypatch,
        {"choices": [{"message": {"content": "  a generated narrative  "}}]},
    )
    result = await text_generation.generate_text(
        provider="custom",
        base_url="https://my-llm.example.com/v1",
        api_key="sk-x",
        model="my-model",
        system_prompt="system",
        user_prompt="user",
    )
    assert result.text == "a generated narrative"
    assert result.model == "my-model"
    assert result.provenance["provider"] == "custom"
    assert result.provenance["endpoint"] == "my-llm.example.com"
    assert _FakeClient.last_kwargs["url"].endswith("/chat/completions")
    assert _FakeClient.last_kwargs["headers"]["Authorization"] == "Bearer sk-x"
    assert _FakeClient.last_client_kwargs["follow_redirects"] is False


async def test_oss_provider_is_keyless(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_client(monkeypatch, {"choices": [{"message": {"content": "hi"}}]})
    result = await text_generation.generate_text(
        provider="oss",
        base_url="https://my-lan-box.example/v1",
        api_key="",
        model="gpt-oss-20b",
        system_prompt="system",
        user_prompt="user",
    )
    assert result.provenance["provider"] == "oss"


async def test_raises_on_no_choices(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_client(monkeypatch, {"choices": []})
    with pytest.raises(
        text_generation.TextGenerationError, match=r"(?i)no completion"
    ):
        await text_generation.generate_text(
            provider="custom",
            base_url="https://my-llm.example.com/v1",
            api_key="sk-x",
            model="my-model",
            system_prompt="system",
            user_prompt="user",
        )


async def test_raises_on_empty_completion(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_client(monkeypatch, {"choices": [{"message": {"content": "   "}}]})
    with pytest.raises(text_generation.TextGenerationError, match=r"(?i)empty"):
        await text_generation.generate_text(
            provider="custom",
            base_url="https://my-llm.example.com/v1",
            api_key="sk-x",
            model="my-model",
            system_prompt="system",
            user_prompt="user",
        )


async def test_response_over_size_cap_is_rejected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(text_generation, "_MAX_RESPONSE_BYTES", 8)
    _patch_client(
        monkeypatch,
        {"choices": [{"message": {"content": "way more than 8 bytes"}}]},
    )
    with pytest.raises(ValueError, match=r"(?i)exceeded"):
        await text_generation.generate_text(
            provider="custom",
            base_url="https://my-llm.example.com/v1",
            api_key="sk-x",
            model="my-model",
            system_prompt="system",
            user_prompt="user",
        )
