"""Single-use password-recovery codes.

Minted once at first-run. The plaintext is shown to the user exactly
once and never persisted; only sha256 hashes of each code live in the
database, comma-separated in `users.password_recovery_codes`.

Each code is 80 bits (20 hex chars). Eight codes per user give the
operator a few attempts in case they wrote one down wrong. Once used,
a code is removed from the stored set — a single recovery event burns
exactly one code.

Format: codes are returned to the UI as 4 groups of 5 hex chars
joined by hyphens (``a1b2c-3d4e5-f6789-0abcd``) for human transcription.
The hyphenated form and the raw form both verify; we strip non-hex
before hashing.
"""

from __future__ import annotations

import hashlib
import secrets

_CODE_COUNT = 8
# 20 hex chars = 80 bits of entropy per code. with the recovery
# endpoint rate-limited to 3/hour, exhaustively guessing one code
# at 3/hour would take ~10^19 years.
_CODE_HEX_CHARS = 20


def generate_codes() -> list[str]:
    """generate the human-facing recovery codes.

    returns the codes in their grouped, hyphenated display form. the
    caller is responsible for hashing them via ``hash_code`` and
    storing the result; the plaintext must never be persisted.
    """
    return [
        _format(secrets.token_hex(_CODE_HEX_CHARS // 2))
        for _ in range(_CODE_COUNT)
    ]


def hash_code(code: str) -> str:
    """sha256-hash a single recovery code.

    accepts either the hyphenated display form or the raw hex; non-hex
    characters and case are normalised away before hashing so users
    can type or paste either form. sha256 (not argon2) is sufficient
    here: each code carries 80 bits of intrinsic entropy, far above
    the threshold where slow hashes meaningfully help.
    """
    normalised = _normalise(code)
    return hashlib.sha256(normalised.encode("ascii")).hexdigest()


def serialize(hashes: list[str]) -> str:
    """pack a list of hex hashes into the column storage format."""
    return ",".join(hashes)


def parse(stored: str | None) -> list[str]:
    """unpack the column value into a list of hashes."""
    if not stored:
        return []
    return [h for h in stored.split(",") if h]


def verify_and_consume(
    stored: str | None,
    candidate: str,
) -> tuple[bool, str | None]:
    """check if ``candidate`` matches one of the stored hashes.

    returns ``(ok, remaining)`` where ``remaining`` is the new column
    value with the matched hash removed, or ``None`` if no codes are
    left. when ``ok`` is False, ``remaining`` is the input unchanged.
    """
    hashes = parse(stored)
    if not hashes:
        return False, stored

    candidate_hash = hash_code(candidate)
    if candidate_hash not in hashes:
        return False, stored

    hashes.remove(candidate_hash)
    return True, serialize(hashes) if hashes else None


def _format(raw_hex: str) -> str:
    # group every 5 chars with hyphens. 20 hex -> 4 groups of 5.
    chunks = [raw_hex[i : i + 5] for i in range(0, len(raw_hex), 5)]
    return "-".join(chunks)


def _normalise(code: str) -> str:
    return "".join(c for c in code.lower() if c in "0123456789abcdef")
