"""at-rest encryption for secrets stored in ``app_settings``.

api keys persisted there (e.g. a user-supplied cloud/self-hosted
provider key) are encrypted with AES-256-GCM. the encryption key is
independent of ``settings.secret_key`` — that key only signs jwts, and
reusing it here would couple api-key decryptability to session-token
rotation. the key comes from ``LOOM_AI_SECRET_KEY`` when set (an
operator, or the desktop shell via tauri-plugin-store), otherwise from a
per-install key file generated on first use under the data dir.

decrypt failure always fails loud — never silently falls back to
treating the value as absent or plaintext. a value written before this
module existed is legacy plaintext and is read through unchanged; the
next save re-encrypts it.
"""

from __future__ import annotations

import base64
import hashlib
import os
import secrets
from pathlib import Path
from typing import Any

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from loom.config import get_settings

_NONCE_LEN = 12
_KEY_LEN = 32
_AAD = b"loom.app_settings.secret.v1"
_KEY_FILE_NAME = "ai_settings.key"
_FORMAT_VERSION = 1


class SecretUnavailableError(Exception):
    """a stored secret exists but can't be decrypted with the current key."""


def _key_file_path() -> Path:
    return get_settings().resolved_data_dir() / "secret" / _KEY_FILE_NAME


def _load_or_create_key_file() -> bytes:
    path = _key_file_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        fd = os.open(str(path), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError:
        return path.read_bytes()
    key = secrets.token_bytes(_KEY_LEN)
    with os.fdopen(fd, "wb") as fh:
        fh.write(key)
    return key


def _encryption_key() -> tuple[bytes, str]:
    """resolve the active key plus a non-secret fingerprint of it.

    the fingerprint lets a decrypt failure tell the user *which* key is
    needed, without exposing the key itself.
    """
    env_key = get_settings().ai_secret_key
    if env_key:
        key = hashlib.sha256(env_key.encode("utf-8")).digest()
        source = "env"
    else:
        key = _load_or_create_key_file()
        source = "file"
    fingerprint = hashlib.sha256(key).hexdigest()[:12]
    return key, f"{source}:{fingerprint}"


def key_id() -> str:
    """non-secret id of the currently-active encryption key.

    settings responses surface this so the ui can flag a stored secret
    as needing re-entry before a decrypt actually fails.
    """
    return _encryption_key()[1]


def encrypt_secret(plaintext: str) -> dict[str, Any] | str:
    """encrypt ``plaintext``; an empty string passes through unchanged
    so "no key configured" stays a plain empty value, not a blob."""
    if not plaintext:
        return ""
    key, kid = _encryption_key()
    nonce = secrets.token_bytes(_NONCE_LEN)
    ciphertext = AESGCM(key).encrypt(nonce, plaintext.encode("utf-8"), _AAD)
    return {
        "v": _FORMAT_VERSION,
        "alg": "A256GCM",
        "key_id": kid,
        "nonce": base64.b64encode(nonce).decode("ascii"),
        "ct": base64.b64encode(ciphertext).decode("ascii"),
    }


def decrypt_secret(stored: Any) -> str:
    """decrypt a value written by :func:`encrypt_secret`.

    ``stored`` may be an encrypted blob, a legacy plaintext string
    (written before this module existed), or empty/missing — the latter
    two pass through as-is. raises :class:`SecretUnavailableError` only
    when ``stored`` is an encrypted blob that fails to decrypt with the
    currently-available key.
    """
    if not stored:
        return ""
    if isinstance(stored, str):
        return stored
    if not isinstance(stored, dict) or stored.get("v") != _FORMAT_VERSION:
        raise SecretUnavailableError("unrecognized stored secret format")
    key, _ = _encryption_key()
    try:
        nonce = base64.b64decode(stored["nonce"])
        ciphertext = base64.b64decode(stored["ct"])
        plaintext = AESGCM(key).decrypt(nonce, ciphertext, _AAD)
    except (KeyError, ValueError, TypeError, InvalidTag) as exc:
        raise SecretUnavailableError(
            "the stored api key can't be decrypted with the current key "
            "(it may have been encrypted on a different machine, or the "
            "key file / LOOM_AI_SECRET_KEY changed) — re-enter it"
        ) from exc
    return plaintext.decode("utf-8")


def is_decryptable(stored: Any) -> bool:
    """true if ``stored`` is empty, legacy plaintext, or decrypts cleanly."""
    try:
        decrypt_secret(stored)
    except SecretUnavailableError:
        return False
    return True
