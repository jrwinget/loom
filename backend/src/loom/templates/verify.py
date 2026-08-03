#!/usr/bin/env python3
"""verify a Loom court bundle without installing Loom.

usage:
    python3 verify.py <bundle.zip or extracted-directory>
    python3 verify.py <bundle> --pubkey <ed25519-public-key.pem>

re-hashes every file listed in MANIFEST.sha256 with SHA-256 using
only the python standard library and reports ok / MISMATCH /
MISSING per file plus an overall verdict. exits 0 only when every
listed file is present and matches.

checking the optional detached signature (MANIFEST.sha256.sig)
needs the third-party `cryptography` package or openssl; when the
package is missing this script prints the exact openssl command
to run instead.
"""

from __future__ import annotations

import argparse
import hashlib
import sys
import zipfile
from pathlib import Path

MANIFEST_NAME = "MANIFEST.sha256"
SIGNATURE_NAME = "MANIFEST.sha256.sig"
_CHUNK = 1024 * 1024


class Bundle:
    """uniform reader over an extracted directory or a zip file."""

    def __init__(self, root: Path) -> None:
        self._zip = None if root.is_dir() else zipfile.ZipFile(root)
        self._dir = root if root.is_dir() else None

    def names(self) -> set[str]:
        if self._zip is not None:
            return {n for n in self._zip.namelist() if not n.endswith("/")}
        assert self._dir is not None
        return {
            p.relative_to(self._dir).as_posix()
            for p in self._dir.rglob("*")
            if p.is_file()
        }

    def read(self, name: str) -> bytes:
        if self._zip is not None:
            return self._zip.read(name)
        assert self._dir is not None
        return (self._dir / name).read_bytes()

    def sha256(self, name: str) -> str:
        # chunked so multi-gigabyte originals never load whole
        digest = hashlib.sha256()
        if self._zip is not None:
            with self._zip.open(name) as fh:
                while chunk := fh.read(_CHUNK):
                    digest.update(chunk)
        else:
            assert self._dir is not None
            with (self._dir / name).open("rb") as fh:
                while chunk := fh.read(_CHUNK):
                    digest.update(chunk)
        return digest.hexdigest()


def parse_manifest(text: str) -> dict[str, str]:
    """parse sha256sum-style lines: '<hex digest>  <path>'."""
    entries: dict[str, str] = {}
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        digest, _, path = line.partition("  ")
        entries[path.lstrip("*")] = digest.lower()
    return entries


def _openssl_hint(pubkey: str) -> str:
    return (
        "    openssl pkeyutl -verify -pubin "
        f"-inkey {pubkey} -rawin "
        f"-in {MANIFEST_NAME} -sigfile {SIGNATURE_NAME}"
    )


def check_signature(
    bundle: Bundle,
    names: set[str],
    manifest: bytes,
    pubkey_path: str | None,
) -> bool:
    """returns False only when a signature is present and provably
    does not match; anything unverifiable is reported, not fatal."""
    if SIGNATURE_NAME not in names:
        print(
            f"note: bundle is not signed (no {SIGNATURE_NAME}); "
            "the file hashes above are still authoritative."
        )
        return True
    if pubkey_path is None:
        print(
            f"note: {SIGNATURE_NAME} is present but no --pubkey was "
            "given; skipping the signature check. with the "
            "preparer's public key you can verify it via:"
        )
        print(_openssl_hint("<public-key.pem>"))
        return True

    signature = bundle.read(SIGNATURE_NAME)
    try:
        from cryptography.exceptions import InvalidSignature
        from cryptography.hazmat.primitives.asymmetric.ed25519 import (
            Ed25519PublicKey,
        )
        from cryptography.hazmat.primitives.serialization import (
            load_pem_public_key,
        )
    except ImportError:
        print(
            "note: the python 'cryptography' package is not "
            "installed; verify the signature with openssl instead:"
        )
        print(_openssl_hint(pubkey_path))
        return True

    key = load_pem_public_key(Path(pubkey_path).read_bytes())
    if not isinstance(key, Ed25519PublicKey):
        print("warning: public key is not Ed25519; cannot verify.")
        return True
    try:
        key.verify(signature, manifest)
    except InvalidSignature:
        print("signature: INVALID — manifest does not match signature")
        return False
    print("signature: VALID (Ed25519)")
    return True


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="verify a Loom court bundle against MANIFEST.sha256"
    )
    parser.add_argument(
        "bundle",
        help="path to the court bundle zip or an extracted directory",
    )
    parser.add_argument(
        "--pubkey",
        help="ed25519 public key (pem) to check MANIFEST.sha256.sig",
    )
    args = parser.parse_args(argv)

    root = Path(args.bundle)
    if not root.exists():
        print(f"error: {root} does not exist", file=sys.stderr)
        return 2

    bundle = Bundle(root)
    names = bundle.names()
    if MANIFEST_NAME not in names:
        print(f"error: no {MANIFEST_NAME} found in {root}", file=sys.stderr)
        return 2

    manifest = bundle.read(MANIFEST_NAME)
    entries = parse_manifest(manifest.decode("utf-8"))

    failures = 0
    for path in sorted(entries):
        if path not in names:
            print(f"MISSING   {path}")
            failures += 1
            continue
        actual = bundle.sha256(path)
        if actual == entries[path]:
            print(f"ok        {path}")
        else:
            print(f"MISMATCH  {path}")
            print(f"          expected {entries[path]}")
            print(f"          actual   {actual}")
            failures += 1

    unlisted = names - set(entries) - {MANIFEST_NAME, SIGNATURE_NAME}
    for path in sorted(unlisted):
        print(f"UNLISTED  {path} (present but not in {MANIFEST_NAME})")

    signature_ok = check_signature(bundle, names, manifest, args.pubkey)

    print()
    if failures:
        print(
            f"FAILED: {failures} of {len(entries)} listed files did not verify."
        )
        return 1
    if not signature_ok:
        print("FAILED: signature did not verify.")
        return 1
    print(f"OK: all {len(entries)} listed files verified.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
