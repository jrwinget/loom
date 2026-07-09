"""the model registry is the only path whisper weights arrive by,
so its verification and atomicity properties are load-bearing: a
torn or tampered download must never be mistakable for an installed
model."""

from __future__ import annotations

import hashlib
from pathlib import Path

import httpx
import pytest

import loom.config
from loom.services import model_registry as reg
from loom.services.engines import EngineUnavailableError


@pytest.fixture(autouse=True)
def _data_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LOOM_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("LOOM_DEPLOYMENT_PROFILE", "lite")
    monkeypatch.setenv(
        "LOOM_DATABASE_URL", f"sqlite+aiosqlite:///{tmp_path}/loom.db"
    )
    monkeypatch.setenv("LOOM_SECRET_KEY", "x" * 48)
    monkeypatch.setenv("LOOM_STORAGE_SIGNING_SECRET", "y" * 48)
    loom.config.get_settings.cache_clear()
    yield
    loom.config.get_settings.cache_clear()


def _tiny_fake_spec() -> tuple[reg.ModelSpec, dict[str, bytes]]:
    payloads = {"config.json": b'{"fake": true}', "model.bin": b"\x00" * 64}
    return reg.ModelSpec(
        name="tiny",
        repo="Systran/faster-whisper-tiny",
        revision="deadbeef",
        files=tuple(
            reg.ModelFile(name, len(body), hashlib.sha256(body).hexdigest())
            for name, body in payloads.items()
        ),
    ), payloads


def _client_for(
    spec: reg.ModelSpec,
    payloads: dict[str, bytes],
    *,
    corrupt: str | None = None,
) -> httpx.AsyncClient:
    def handler(request: httpx.Request) -> httpx.Response:
        name = request.url.path.rsplit("/", 1)[-1]
        body = payloads[name]
        if name == corrupt:
            body = body + b"tampered"
        return httpx.Response(200, content=body)

    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


def test_catalog_manifests_are_well_formed() -> None:
    for name, spec in reg.WHISPER_MODELS.items():
        assert spec.name == name
        assert spec.revision and len(spec.revision) == 40
        filenames = {f.name for f in spec.files}
        assert {"config.json", "model.bin", "tokenizer.json"} <= filenames
        for file in spec.files:
            assert file.size > 0
            assert len(file.sha256) == 64
            int(file.sha256, 16)


def test_unknown_model_rejected() -> None:
    with pytest.raises(KeyError, match="unknown whisper model"):
        reg.get_spec("gigantic")


def test_resolve_raises_engine_unavailable_when_missing() -> None:
    with pytest.raises(EngineUnavailableError) as exc:
        reg.resolve_model_dir("base")
    assert exc.value.engine == "transcription"
    assert "download" in exc.value.remedy.lower()


@pytest.mark.asyncio
async def test_download_verifies_and_installs_atomically(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    spec, payloads = _tiny_fake_spec()
    monkeypatch.setitem(reg.WHISPER_MODELS, "tiny", spec)
    progress: list[tuple[int, int]] = []

    async with _client_for(spec, payloads) as client:
        path = await reg.download_model(
            "tiny",
            on_progress=lambda d, t: progress.append((d, t)),
            client=client,
        )

    assert path == reg.model_dir("tiny")
    assert reg.is_downloaded("tiny")
    assert reg.installed_models() == ["tiny"]
    assert reg.resolve_model_dir("tiny") == path
    assert (path / "model.bin").read_bytes() == payloads["model.bin"]
    # progress is monotonic and ends at the full total
    assert progress and progress[-1] == (spec.total_bytes, spec.total_bytes)
    # no partial directory left behind
    assert not list(reg.models_root().glob(".partial-*"))


@pytest.mark.asyncio
async def test_tampered_download_installs_nothing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    spec, payloads = _tiny_fake_spec()
    monkeypatch.setitem(reg.WHISPER_MODELS, "tiny", spec)

    async with _client_for(spec, payloads, corrupt="model.bin") as client:
        with pytest.raises(reg.ModelVerificationError):
            await reg.download_model("tiny", client=client)

    assert not reg.is_downloaded("tiny")
    assert not reg.model_dir("tiny").exists()
    assert not list(reg.models_root().glob(".partial-*"))


@pytest.mark.asyncio
async def test_download_is_idempotent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    spec, payloads = _tiny_fake_spec()
    monkeypatch.setitem(reg.WHISPER_MODELS, "tiny", spec)

    async with _client_for(spec, payloads) as client:
        await reg.download_model("tiny", client=client)

    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(500)

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler)
    ) as client:
        path = await reg.download_model("tiny", client=client)

    assert calls == 0, "already-downloaded model must not refetch"
    assert path == reg.model_dir("tiny")


def test_delete_model(monkeypatch: pytest.MonkeyPatch) -> None:
    spec, _ = _tiny_fake_spec()
    monkeypatch.setitem(reg.WHISPER_MODELS, "tiny", spec)
    target = reg.model_dir("tiny")
    target.mkdir(parents=True)
    (target / "model.bin").write_bytes(b"\x00" * 64)

    reg.delete_model("tiny")
    assert not target.exists()
    assert reg.installed_models() == []
