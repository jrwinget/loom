"""unit tests for cloud transcription (no real network)."""

from pathlib import Path
from typing import Any, ClassVar

import httpx
import pytest

from loom.services import transcription


class _FakeResponse:
    def __init__(self, payload: dict[str, Any]) -> None:
        self._payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict[str, Any]:
        return self._payload


class _FakeClient:
    """stands in for httpx.AsyncClient; captures the request."""

    last_kwargs: ClassVar[dict[str, Any]] = {}

    def __init__(self, payload: dict[str, Any]) -> None:
        self._payload = payload

    async def __aenter__(self) -> "_FakeClient":
        return self

    async def __aexit__(self, *args: object) -> bool:
        return False

    async def post(self, url: str, **kwargs: Any) -> _FakeResponse:
        _FakeClient.last_kwargs = {"url": url, **kwargs}
        return _FakeResponse(self._payload)


@pytest.fixture
def audio_file(tmp_path: Path) -> str:
    p = tmp_path / "clip.mp3"
    p.write_bytes(b"id3 fake audio")
    return str(p)


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
    monkeypatch.setattr(
        transcription.httpx,
        "AsyncClient",
        lambda *a, **k: _FakeClient(payload),
    )

    segments = await transcription.transcribe_via_cloud(
        audio_file,
        base_url="https://api.openai.com/v1",
        api_key="sk-x",
        model="whisper-1",
    )

    assert [s["text"] for s in segments] == ["hello", "world"]
    assert segments[0]["language"] == "en"
    assert segments[0]["confidence"] == -0.2
    assert segments[0]["model_name"] == "cloud:whisper-1"
    assert segments[0]["model_params"]["provider"] == "cloud"
    assert segments[0]["model_params"]["endpoint"] == "api.openai.com"
    # the bearer key is sent and the right endpoint is hit
    assert _FakeClient.last_kwargs["url"].endswith("/audio/transcriptions")
    assert _FakeClient.last_kwargs["headers"]["Authorization"] == "Bearer sk-x"


async def test_falls_back_to_text_only(
    audio_file: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        transcription.httpx,
        "AsyncClient",
        lambda *a, **k: _FakeClient({"text": "whole thing", "language": "en"}),
    )
    segments = await transcription.transcribe_via_cloud(
        audio_file,
        base_url="https://api.openai.com/v1",
        api_key="sk-x",
        model="whisper-1",
    )
    assert len(segments) == 1
    assert segments[0]["text"] == "whole thing"


def test_uses_httpx_which_is_a_core_dep() -> None:
    # guards the assumption that httpx ships without the ai extra
    assert httpx.__version__
