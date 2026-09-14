"""unit tests for cloud/self-hosted transcription (no real network)."""

import json
from pathlib import Path
from typing import Any, ClassVar

import httpx
import pytest

from loom.services import transcription


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
    """stands in for httpx.AsyncClient; captures the request."""

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
    # these tests exercise the http dispatch/parsing logic, not ssrf
    # validation (covered in test_ai_config.py) — a real dns lookup here
    # would make unit tests network-dependent and flaky.
    monkeypatch.setattr(
        transcription, "assert_resolved_host_safe", lambda *a, **k: None
    )


@pytest.fixture
def audio_file(tmp_path: Path) -> str:
    p = tmp_path / "clip.mp3"
    p.write_bytes(b"id3 fake audio")
    return str(p)


def _patch_client(
    monkeypatch: pytest.MonkeyPatch, payload: dict[str, Any]
) -> None:
    def _make_client(*_a: object, **kwargs: object) -> _FakeClient:
        _FakeClient.last_client_kwargs = dict(kwargs)
        return _FakeClient(payload)

    monkeypatch.setattr(transcription.httpx, "AsyncClient", _make_client)


async def test_parses_verbose_json_segments(
    audio_file: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    payload = {
        "language": "en",
        "segments": [
            {"start": 0.0, "end": 1.5, "text": " hello", "avg_logprob": -0.2},
            {"start": 1.5, "end": 3.0, "text": " world", "avg_logprob": -0.3},
        ],
    }
    _patch_client(monkeypatch, payload)

    segments = await transcription.transcribe_via_cloud(
        audio_file,
        provider="custom",
        base_url="https://transcribe.example.com/v1",
        api_key="sk-x",
        model="whisper-1",
    )

    assert [s["text"] for s in segments] == ["hello", "world"]
    assert segments[0]["language"] == "en"
    assert segments[0]["confidence"] == -0.2
    assert segments[0]["model_name"] == "cloud:whisper-1"
    assert segments[0]["model_params"]["provider"] == "custom"
    assert segments[0]["model_params"]["endpoint"] == "transcribe.example.com"
    # the bearer key is sent and the right endpoint is hit
    assert _FakeClient.last_kwargs["url"].endswith("/audio/transcriptions")
    assert _FakeClient.last_kwargs["headers"]["Authorization"] == "Bearer sk-x"
    # a validated endpoint must never be silently redirected elsewhere
    assert _FakeClient.last_client_kwargs["follow_redirects"] is False


async def test_falls_back_to_text_only(
    audio_file: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_client(monkeypatch, {"text": "whole thing", "language": "en"})
    segments = await transcription.transcribe_via_cloud(
        audio_file,
        provider="custom",
        base_url="https://transcribe.example.com/v1",
        api_key="sk-x",
        model="whisper-1",
    )
    assert len(segments) == 1
    assert segments[0]["text"] == "whole thing"


async def test_self_hosted_oss_provider_is_keyless(
    audio_file: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_client(monkeypatch, {"text": "local server result"})
    segments = await transcription.transcribe_via_cloud(
        audio_file,
        provider="oss",
        base_url="https://my-lan-box.example/v1",
        api_key="",
        model="whisper-large-v3",
    )
    assert segments[0]["text"] == "local server result"
    assert segments[0]["model_params"]["provider"] == "oss"


async def test_response_over_size_cap_is_rejected(
    audio_file: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(transcription, "_MAX_RESPONSE_BYTES", 8)
    _patch_client(
        monkeypatch,
        {"text": "this response body is definitely longer than 8 bytes"},
    )
    with pytest.raises(ValueError, match=r"(?i)exceeded"):
        await transcription.transcribe_via_cloud(
            audio_file,
            provider="custom",
            base_url="https://transcribe.example.com/v1",
            api_key="sk-x",
            model="whisper-1",
        )


def test_uses_httpx_which_is_a_core_dep() -> None:
    # guards the assumption that httpx ships without the ai extra
    assert httpx.__version__
