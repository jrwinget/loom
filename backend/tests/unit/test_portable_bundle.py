"""the portable bundle carries a whole case to another Loom, so its
manifest coverage, tamper detection, and signature handling are
load-bearing: a corrupt or tampered bundle must never verify."""

from __future__ import annotations

import zipfile
from collections.abc import Iterator
from pathlib import Path
from uuid import uuid4

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
)
from cryptography.hazmat.primitives.serialization import (
    Encoding,
    NoEncryption,
    PrivateFormat,
    PublicFormat,
)
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from loom.models.asset import Asset
from loom.models.base import Base
from loom.models.case import Case
from loom.models.chain_of_custody import ChainOfCustodyEntry
from loom.services import portable_bundle as pb


class _FakeStorage:
    """serves asset bytes by storage key; enough of the backend
    protocol for the exporter's get_object_stream."""

    def __init__(self, objects: dict[str, bytes]) -> None:
        self._objects = objects

    def get_object_stream(
        self, bucket: str, key: str, chunk_size: int = 65536
    ) -> tuple[int, Iterator[bytes]]:
        data = self._objects[key]

        def gen() -> Iterator[bytes]:
            for i in range(0, len(data), chunk_size):
                yield data[i : i + chunk_size]

        return len(data), gen()


def _keypair() -> tuple[str, str]:
    key = Ed25519PrivateKey.generate()
    priv = key.private_bytes(
        Encoding.PEM, PrivateFormat.PKCS8, NoEncryption()
    ).decode()
    pub = (
        key.public_key()
        .public_bytes(Encoding.PEM, PublicFormat.SubjectPublicKeyInfo)
        .decode()
    )
    return priv, pub


@pytest.fixture
async def session() -> AsyncSession:
    engine = create_async_engine("sqlite+aiosqlite://")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as s:
        yield s
    await engine.dispose()


async def _seed(session: AsyncSession) -> tuple[str, _FakeStorage]:
    actor = uuid4()
    case = Case(name="Portable Case", created_by=actor, status="active")
    session.add(case)
    await session.flush()

    payload = b"evidence bytes for the portable bundle test\n"
    import hashlib

    sha = hashlib.sha256(payload).hexdigest()
    asset = Asset(
        case_id=case.id,
        original_filename="clip.txt",
        storage_key=f"{case.id}/{uuid4()}/clip.txt",
        media_type="document",
        mime_type="text/plain",
        file_size_bytes=len(payload),
        sha256_hash=sha,
        sha512_hash=hashlib.sha512(payload).hexdigest(),
        uploaded_by=actor,
        upload_status="complete",
        processing_status="complete",
    )
    session.add(asset)
    await session.flush()
    session.add(
        ChainOfCustodyEntry(
            asset_id=asset.id, action="upload", actor_id=actor, detail={}
        )
    )
    await session.flush()
    return str(case.id), _FakeStorage({asset.storage_key: payload})


async def test_build_produces_verifiable_signed_bundle(
    session: AsyncSession, tmp_path: Path
) -> None:
    case_id, storage = await _seed(session)
    priv, pub = _keypair()
    dest = tmp_path / "bundle.zip"

    sha = await pb.build_portable_bundle(
        session, case_id, storage, dest, signing_key_pem=priv
    )
    assert len(sha) == 64
    assert dest.is_file()

    with zipfile.ZipFile(dest) as zf:
        names = set(zf.namelist())
    assert "MANIFEST.sha256" in names
    assert "MANIFEST.sha256.sig" in names
    assert "bundle.json" in names
    assert "data/case.json" in names
    assert "data/custody.json" in names
    assert any(n.startswith("evidence/") for n in names)

    # a configured trusted key verifies the manifest end to end
    status = pb.verify_bundle(dest, trusted_keys_pem=[pub])
    assert status.state == "signed_trusted"


async def test_unsigned_bundle_verifies_as_unsigned(
    session: AsyncSession, tmp_path: Path
) -> None:
    case_id, storage = await _seed(session)
    dest = tmp_path / "bundle.zip"
    await pb.build_portable_bundle(session, case_id, storage, dest)

    status = pb.verify_bundle(dest, trusted_keys_pem=[])
    assert status.state == "unsigned"


async def test_signed_bundle_with_no_trusted_key_is_untrusted(
    session: AsyncSession, tmp_path: Path
) -> None:
    case_id, storage = await _seed(session)
    priv, _pub = _keypair()
    _other_priv, other_pub = _keypair()
    dest = tmp_path / "bundle.zip"
    await pb.build_portable_bundle(
        session, case_id, storage, dest, signing_key_pem=priv
    )

    # a real signature, but signed by a key we do not trust — import
    # proceeds, the status records the gap
    status = pb.verify_bundle(dest, trusted_keys_pem=[other_pub])
    assert status.state == "signed_untrusted"


async def test_tampered_evidence_fails_verification(
    session: AsyncSession, tmp_path: Path
) -> None:
    case_id, storage = await _seed(session)
    dest = tmp_path / "bundle.zip"
    await pb.build_portable_bundle(session, case_id, storage, dest)

    # rewrite the zip with one evidence entry mutated
    tampered = tmp_path / "tampered.zip"
    with (
        zipfile.ZipFile(dest) as src,
        zipfile.ZipFile(tampered, "w") as dst,
    ):
        for name in src.namelist():
            data = src.read(name)
            if name.startswith("evidence/"):
                data = data + b"tamper"
            dst.writestr(name, data)

    with pytest.raises(pb.BundleVerificationError, match="mismatch"):
        pb.verify_bundle(tampered)


async def test_missing_manifest_fails(
    session: AsyncSession, tmp_path: Path
) -> None:
    case_id, storage = await _seed(session)
    dest = tmp_path / "bundle.zip"
    await pb.build_portable_bundle(session, case_id, storage, dest)

    stripped = tmp_path / "stripped.zip"
    with (
        zipfile.ZipFile(dest) as src,
        zipfile.ZipFile(stripped, "w") as dst,
    ):
        for name in src.namelist():
            if name != "MANIFEST.sha256":
                dst.writestr(name, src.read(name))

    with pytest.raises(pb.BundleVerificationError, match="MANIFEST"):
        pb.verify_bundle(stripped)
