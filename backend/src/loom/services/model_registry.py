"""whisper model registry: pinned manifests, explicit downloads.

model weights are neither bundled (installer bloat) nor fetched
implicitly on first transcribe (surprise egress from an app that
promises none). the catalog pins every file to a specific
huggingface revision and sha256; downloads happen only on explicit
admin action, land under ``<data_dir>/models/whisper/<name>``, and
loads hand faster-whisper the local directory so the engine never
reaches the network on its own.
"""

from __future__ import annotations

import hashlib
import os
import shutil
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import httpx

from loom.config import get_settings

_HF_BASE = "https://huggingface.co"
_DOWNLOAD_TIMEOUT_S = 600.0


@dataclass(frozen=True)
class ModelFile:
    name: str
    size: int
    sha256: str


@dataclass(frozen=True)
class ModelSpec:
    name: str
    repo: str
    revision: str
    files: tuple[ModelFile, ...]

    @property
    def total_bytes(self) -> int:
        return sum(f.size for f in self.files)

    def file_url(self, file: ModelFile) -> str:
        return f"{_HF_BASE}/{self.repo}/resolve/{self.revision}/{file.name}"


# pinned 2026-07-08 from the Systran ctranslate2 conversions. sizes
# and hashes come from the hub api at the pinned revision; bumping a
# model means updating the revision and every hash together.
WHISPER_MODELS: dict[str, ModelSpec] = {
    "tiny": ModelSpec(
        name="tiny",
        repo="Systran/faster-whisper-tiny",
        revision="d90ca5fe260221311c53c58e660288d3deb8d356",
        files=(
            ModelFile(
                "config.json",
                2249,
                "a73a28cdfe1c43ccc7202fa333d1f89c"
                "202477271407ae9a7f19afa52039cac8",
            ),
            ModelFile(
                "model.bin",
                75538270,
                "dcb76c6586fc06cbdac6dd21f14cfd12"
                "9cc4cdd9dce19bf4ffa62e59cbe6e6d1",
            ),
            ModelFile(
                "tokenizer.json",
                2203239,
                "fb7b63191e9bb045082c79fd742a3106"
                "a12c99513ab30df4a0d47fa6cb6fd0ab",
            ),
            ModelFile(
                "vocabulary.txt",
                459861,
                "34ce3fe1c5041027b3f8d42912270993"
                "f986dbc4bb34cf27f951e34a1e453913",
            ),
        ),
    ),
    "base": ModelSpec(
        name="base",
        repo="Systran/faster-whisper-base",
        revision="ebe41f70d5b6dfa9166e2c581c45c9c0cfc57b66",
        files=(
            ModelFile(
                "config.json",
                2309,
                "56a6d8110d311f19c8f0471e562832c7"
                "527f146b567275bfca59fcf7c184da9a",
            ),
            ModelFile(
                "model.bin",
                145217532,
                "d01c3014881c9c6f3133c182f3d2887e"
                "b6ca1c789a7538c5c007196857a0a6a9",
            ),
            ModelFile(
                "tokenizer.json",
                2203239,
                "fb7b63191e9bb045082c79fd742a3106"
                "a12c99513ab30df4a0d47fa6cb6fd0ab",
            ),
            ModelFile(
                "vocabulary.txt",
                459861,
                "34ce3fe1c5041027b3f8d42912270993"
                "f986dbc4bb34cf27f951e34a1e453913",
            ),
        ),
    ),
    "small": ModelSpec(
        name="small",
        repo="Systran/faster-whisper-small",
        revision="536b0662742c02347bc0e980a01041f333bce120",
        files=(
            ModelFile(
                "config.json",
                2370,
                "b55496ac7940a7ae47d2c01eab40edfd"
                "8701feec1229d9cce3b40014383fb828",
            ),
            ModelFile(
                "model.bin",
                483546902,
                "3e305921506d8872816023e4c273e75d"
                "2419fb89b24da97b4fe7bce14170d671",
            ),
            ModelFile(
                "tokenizer.json",
                2203239,
                "fb7b63191e9bb045082c79fd742a3106"
                "a12c99513ab30df4a0d47fa6cb6fd0ab",
            ),
            ModelFile(
                "vocabulary.txt",
                459861,
                "34ce3fe1c5041027b3f8d42912270993"
                "f986dbc4bb34cf27f951e34a1e453913",
            ),
        ),
    ),
}


class ModelVerificationError(RuntimeError):
    """a downloaded file did not match its pinned size or sha256."""


def models_root() -> Path:
    return get_settings().resolved_data_dir() / "models" / "whisper"


def model_dir(name: str) -> Path:
    return models_root() / name


def get_spec(name: str) -> ModelSpec:
    try:
        return WHISPER_MODELS[name]
    except KeyError as exc:
        known = ", ".join(sorted(WHISPER_MODELS))
        raise KeyError(
            f"unknown whisper model {name!r} (have: {known})"
        ) from exc


def is_downloaded(name: str) -> bool:
    """cheap presence check: every file exists with its pinned size.

    full hashes are verified once at download time; this runs on
    every probe/status call so it stays at stat() cost.
    """
    spec = get_spec(name)
    root = model_dir(name)
    for file in spec.files:
        path = root / file.name
        if not path.is_file() or path.stat().st_size != file.size:
            return False
    return True


def installed_models() -> list[str]:
    return [name for name in WHISPER_MODELS if is_downloaded(name)]


def delete_model(name: str) -> None:
    get_spec(name)
    shutil.rmtree(model_dir(name), ignore_errors=True)


def resolve_model_dir(name: str) -> Path:
    """return the local directory for a downloaded model, or fail loud.

    imported lazily by the transcription service so the remedy shows
    up as a normal engine failure in job status and asset
    processing_error.
    """
    from loom.services.engines import (
        REMEDY_WHISPER_MODEL,
        EngineUnavailableError,
    )

    get_spec(name)
    if not is_downloaded(name):
        raise EngineUnavailableError("transcription", REMEDY_WHISPER_MODEL)
    return model_dir(name)


async def download_model(
    name: str,
    *,
    on_progress: Callable[[int, int], None] | None = None,
    client: httpx.AsyncClient | None = None,
) -> Path:
    """download and verify one model, atomically.

    files stream into a sibling ``.partial-<name>`` directory with
    incremental sha256; only after every file verifies does the
    directory move into place, so a torn download can never be
    mistaken for an installed model. ``on_progress`` receives
    ``(bytes_done, bytes_total)`` across the whole model.
    """
    spec = get_spec(name)
    final = model_dir(name)
    if is_downloaded(name):
        return final

    partial = models_root() / f".partial-{name}"
    shutil.rmtree(partial, ignore_errors=True)
    partial.mkdir(parents=True, exist_ok=True)

    owns_client = client is None
    if client is None:
        client = httpx.AsyncClient(
            timeout=_DOWNLOAD_TIMEOUT_S, follow_redirects=True
        )
    done = 0
    try:
        for file in spec.files:
            digest = hashlib.sha256()
            dest = partial / file.name
            async with client.stream("GET", spec.file_url(file)) as resp:
                resp.raise_for_status()
                with dest.open("wb") as fh:
                    async for chunk in resp.aiter_bytes():
                        fh.write(chunk)
                        digest.update(chunk)
                        done += len(chunk)
                        if on_progress is not None:
                            on_progress(done, spec.total_bytes)
            if dest.stat().st_size != file.size:
                raise ModelVerificationError(
                    f"{file.name}: size {dest.stat().st_size}, "
                    f"expected {file.size}"
                )
            if digest.hexdigest() != file.sha256:
                raise ModelVerificationError(
                    f"{file.name}: sha256 mismatch against the pinned "
                    "manifest — refusing to install"
                )
        shutil.rmtree(final, ignore_errors=True)
        os.replace(partial, final)
        return final
    except BaseException:
        shutil.rmtree(partial, ignore_errors=True)
        raise
    finally:
        if owns_client:
            await client.aclose()
