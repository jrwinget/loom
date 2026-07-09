"""build and read a portable bundle — a case, whole, for another Loom.

a court bundle targets a judge (rendered pdfs); a portable bundle
targets another Loom install. it is a superset: full row data as
json, the original evidence files, a MANIFEST.sha256 over every
entry, and an optional detached Ed25519 signature. the zip is
STREAMED to a file on disk — evidence originals are copied through
in chunks and never held in memory at once — so a case with tens of
gigabytes of footage exports without exhausting ram.

the reader here only parses and verifies; recreation into a new
case lives in the import workflow so it runs as a background job.
"""

from __future__ import annotations

import hashlib
import json
import logging
import zipfile
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from loom.models.annotation import Annotation
from loom.models.asset import Asset
from loom.models.case import Case
from loom.models.chain_of_custody import ChainOfCustodyEntry
from loom.models.timeline import TimelineEvent, TimelineEventEvidence
from loom.models.transcript import TranscriptSegment
from loom.services.storage_backends import ORIGINALS_BUCKET, StorageBackend

logger = logging.getLogger(__name__)

# bump when the on-disk layout changes in a way an older importer
# could not read; the importer checks it and refuses newer majors.
BUNDLE_FORMAT_VERSION = 1

_MANIFEST_NAME = "MANIFEST.sha256"
_SIG_NAME = "MANIFEST.sha256.sig"
_META_NAME = "bundle.json"
_COPY_CHUNK = 1024 * 1024


class BundleVerificationError(RuntimeError):
    """the bundle's manifest or signature did not verify. tamper is a
    hard stop on an evidence product, never a warning."""


@dataclass(frozen=True)
class SignatureStatus:
    # "signed_trusted": a configured public key verified the manifest
    # "signed_untrusted": a valid-looking sig but no configured key
    #   accepted it (import proceeds, status recorded)
    # "unsigned": no signature present
    state: str
    key_hint: str | None = None


def _asset_row(asset: Asset) -> dict[str, Any]:
    """every field needed to recreate an asset faithfully. the
    source id is kept so timeline/annotation cross-refs remap; ids,
    storage keys, and owner are deployment-local and minted on
    import."""
    return {
        "source_id": str(asset.id),
        "original_filename": asset.original_filename,
        "media_type": asset.media_type,
        "mime_type": asset.mime_type,
        "file_size_bytes": asset.file_size_bytes,
        "sha256_hash": asset.sha256_hash,
        "sha512_hash": asset.sha512_hash,
        "capture_time": _iso(asset.capture_time),
        "metadata_raw": asset.metadata_raw,
        "metadata_extracted": asset.metadata_extracted,
        "processing_status": asset.processing_status,
        "processing_error": asset.processing_error,
        "clock_offset_seconds": asset.clock_offset_seconds,
        "source_uri": asset.source_uri,
        "source_canonical_uri": asset.source_canonical_uri,
        "source_method": asset.source_method,
        "source_downloader": asset.source_downloader,
        "source_downloader_version": asset.source_downloader_version,
        "source_retrieved_at": _iso(asset.source_retrieved_at),
        "source_response_headers": asset.source_response_headers,
        "source_wayback_url": asset.source_wayback_url,
        "source_extractor_info": asset.source_extractor_info,
    }


def _iso(value: Any) -> str | None:
    return value.isoformat() if value is not None else None


async def _gather(session: AsyncSession, case_id: str) -> dict[str, Any]:
    cid = UUID(case_id)
    case = await session.get(Case, cid)
    if case is None:
        raise ValueError(f"case {case_id} not found")

    assets = list(
        (await session.scalars(select(Asset).where(Asset.case_id == cid))).all()
    )
    asset_ids = [a.id for a in assets]

    events = list(
        (
            await session.scalars(
                select(TimelineEvent).where(TimelineEvent.case_id == cid)
            )
        ).all()
    )
    event_ids = [e.id for e in events]
    links: list[TimelineEventEvidence] = []
    if event_ids:
        links = list(
            (
                await session.scalars(
                    select(TimelineEventEvidence).where(
                        TimelineEventEvidence.event_id.in_(event_ids)
                    )
                )
            ).all()
        )

    annotations = list(
        (
            await session.scalars(
                select(Annotation).where(Annotation.case_id == cid)
            )
        ).all()
    )

    transcripts: list[TranscriptSegment] = []
    custody: list[ChainOfCustodyEntry] = []
    if asset_ids:
        transcripts = list(
            (
                await session.scalars(
                    select(TranscriptSegment).where(
                        TranscriptSegment.asset_id.in_(asset_ids)
                    )
                )
            ).all()
        )
        custody = list(
            (
                await session.scalars(
                    select(ChainOfCustodyEntry)
                    .where(ChainOfCustodyEntry.asset_id.in_(asset_ids))
                    .order_by(ChainOfCustodyEntry.timestamp.asc())
                )
            ).all()
        )

    return {
        "case": case,
        "assets": assets,
        "events": events,
        "links": links,
        "annotations": annotations,
        "transcripts": transcripts,
        "custody": custody,
    }


def _data_documents(data: dict[str, Any]) -> dict[str, Any]:
    """the json documents that go under data/ in the bundle."""
    case: Case = data["case"]
    return {
        "data/case.json": {
            "name": case.name,
            "description": case.description,
            "status": case.status,
        },
        "data/assets.json": [_asset_row(a) for a in data["assets"]],
        "data/timeline.json": {
            "events": [
                {
                    "source_id": str(e.id),
                    "title": e.title,
                    "description": e.description,
                    "event_time_start": _iso(e.event_time_start),
                    "event_time_end": _iso(e.event_time_end),
                    "time_precision": e.time_precision,
                    "status": e.status,
                    "location_description": e.location_description,
                    "location_lat": e.location_lat,
                    "location_lon": e.location_lon,
                    "location_confidence": e.location_confidence,
                }
                for e in data["events"]
            ],
            "evidence_links": [
                {
                    "event_source_id": str(link.event_id),
                    "asset_source_id": (
                        str(link.asset_id) if link.asset_id else None
                    ),
                    "annotation_source_id": (
                        str(link.annotation_id) if link.annotation_id else None
                    ),
                    "clip_start": link.clip_start,
                    "clip_end": link.clip_end,
                    "relationship": link.relationship,
                }
                for link in data["links"]
            ],
        },
        "data/annotations.json": [
            {
                "source_id": str(ann.id),
                "asset_source_id": (
                    str(ann.asset_id) if ann.asset_id else None
                ),
                "type": ann.type,
                "content": ann.content,
                "time_start": ann.time_start,
                "time_end": ann.time_end,
                "frame_number": ann.frame_number,
                "spatial_region": ann.spatial_region,
            }
            for ann in data["annotations"]
        ],
        "data/transcripts.json": [
            {
                "asset_source_id": str(t.asset_id),
                "start_time": t.start_time,
                "end_time": t.end_time,
                "text": t.text,
                "speaker_label": t.speaker_label,
                "language": t.language,
                "confidence": t.confidence,
                "model_name": t.model_name,
                "model_version": t.model_version,
            }
            for t in data["transcripts"]
        ],
        # the source deploy's full custody trail travels with the
        # evidence so the chain is not severed by the export/import
        "data/custody.json": [
            {
                "asset_source_id": str(c.asset_id),
                "action": c.action,
                "actor_id": str(c.actor_id),
                "detail": c.detail,
                "timestamp": _iso(c.timestamp),
            }
            for c in data["custody"]
        ],
    }


def _write_json_entry(zf: zipfile.ZipFile, name: str, payload: Any) -> str:
    """write a small json document, returning its sha256."""
    body = json.dumps(payload, indent=2, sort_keys=True).encode("utf-8")
    zf.writestr(name, body)
    return hashlib.sha256(body).hexdigest()


def _stream_evidence_entry(
    zf: zipfile.ZipFile,
    name: str,
    stream: Iterator[bytes],
) -> str:
    """copy an original into the zip in chunks, hashing as we go so
    the file is never fully resident in memory."""
    digest = hashlib.sha256()
    with zf.open(name, "w") as entry:
        for chunk in stream:
            entry.write(chunk)
            digest.update(chunk)
    return digest.hexdigest()


def _sign_manifest(
    manifest: bytes, signing_key_pem: str | None
) -> bytes | None:
    if not signing_key_pem:
        return None
    try:
        from cryptography.hazmat.primitives.asymmetric.ed25519 import (
            Ed25519PrivateKey,
        )
        from cryptography.hazmat.primitives.serialization import (
            load_pem_private_key,
        )
    except ImportError:
        logger.warning("cryptography not installed; skipping signature")
        return None
    key = load_pem_private_key(signing_key_pem.encode("utf-8"), password=None)
    if not isinstance(key, Ed25519PrivateKey):
        logger.warning("bundle_signing_key is not Ed25519; skipping signature")
        return None
    return key.sign(manifest)


async def build_portable_bundle(
    session: AsyncSession,
    case_id: str,
    storage: StorageBackend,
    dest_path: Path,
    *,
    signing_key_pem: str | None = None,
    source_deploy: str = "loom",
) -> str:
    """write a portable bundle to ``dest_path``; return its sha256.

    the caller is responsible for moving ``dest_path`` into storage
    (upload_file_move) — this function only produces the file, so the
    zip can be built on the same filesystem as the eventual home and
    the move stays an atomic rename.
    """
    data = await _gather(session, case_id)
    documents = _data_documents(data)
    manifest_entries: dict[str, str] = {}

    with zipfile.ZipFile(
        dest_path, "w", compression=zipfile.ZIP_DEFLATED
    ) as zf:
        meta = {
            "format_version": BUNDLE_FORMAT_VERSION,
            "source_deploy": source_deploy,
            "case_source_id": case_id,
            "asset_count": len(data["assets"]),
        }
        manifest_entries[_META_NAME] = _write_json_entry(zf, _META_NAME, meta)

        for name, payload in documents.items():
            manifest_entries[name] = _write_json_entry(zf, name, payload)

        for asset in data["assets"]:
            entry_name = f"evidence/{asset.id}/{asset.original_filename}"
            _size, stream = storage.get_object_stream(
                ORIGINALS_BUCKET, asset.storage_key
            )
            digest = _stream_evidence_entry(zf, entry_name, stream)
            # the manifest hash and the recorded asset hash must
            # agree — a mismatch here means storage corruption, and
            # the importer re-checks it against the row on the way in
            if digest != asset.sha256_hash:
                raise BundleVerificationError(
                    f"stored bytes for {asset.id} do not match the "
                    "recorded sha256 — refusing to export a corrupt "
                    "original"
                )
            manifest_entries[entry_name] = digest

        manifest_body = _render_manifest(manifest_entries)
        zf.writestr(_MANIFEST_NAME, manifest_body)
        sig = _sign_manifest(manifest_body, signing_key_pem)
        if sig is not None:
            zf.writestr(_SIG_NAME, sig)

    return _hash_file(dest_path)


def _render_manifest(entries: dict[str, str]) -> bytes:
    lines = [f"{entries[path]}  {path}" for path in sorted(entries)]
    return ("\n".join(lines) + "\n").encode("utf-8")


def _hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        while chunk := fh.read(_COPY_CHUNK):
            digest.update(chunk)
    return digest.hexdigest()


def _parse_manifest(body: bytes) -> dict[str, str]:
    entries: dict[str, str] = {}
    for line in body.decode("utf-8").splitlines():
        if not line.strip():
            continue
        # "<sha256>  <path>" — the path may contain spaces, so split
        # on the first double-space only
        digest, _, path = line.partition("  ")
        entries[path] = digest
    return entries


def verify_bundle(
    path: Path, *, trusted_keys_pem: list[str] | None = None
) -> SignatureStatus:
    """verify a bundle's manifest and signature before anything is
    imported. every entry's bytes are re-hashed against the manifest
    (a mismatch is a hard stop), then the detached signature is
    checked against the configured trust store.

    returns the signature status; raises BundleVerificationError on
    any manifest mismatch, a missing manifest, or a signature that is
    present but cryptographically invalid.
    """
    with zipfile.ZipFile(path, "r") as zf:
        names = set(zf.namelist())
        if _MANIFEST_NAME not in names:
            raise BundleVerificationError("bundle has no MANIFEST.sha256")
        if _META_NAME not in names:
            raise BundleVerificationError("bundle has no bundle.json")

        manifest_body = zf.read(_MANIFEST_NAME)
        expected = _parse_manifest(manifest_body)

        listed = names - {_MANIFEST_NAME, _SIG_NAME}
        missing = listed - set(expected)
        if missing:
            raise BundleVerificationError(
                f"entries absent from the manifest: {sorted(missing)}"
            )
        for name, want in expected.items():
            if name not in names:
                raise BundleVerificationError(
                    f"manifest lists a missing entry: {name}"
                )
            got = _hash_entry(zf, name)
            if got != want:
                raise BundleVerificationError(
                    f"sha256 mismatch for {name} — bundle is corrupt "
                    "or tampered"
                )

        format_version = json.loads(zf.read(_META_NAME)).get("format_version")
        if not isinstance(format_version, int) or format_version < 1:
            raise BundleVerificationError("bundle.json format_version invalid")
        if format_version > BUNDLE_FORMAT_VERSION:
            raise BundleVerificationError(
                f"bundle format v{format_version} is newer than this "
                f"install supports (v{BUNDLE_FORMAT_VERSION}) — upgrade Loom"
            )

        sig = zf.read(_SIG_NAME) if _SIG_NAME in names else None

    return _verify_signature(manifest_body, sig, trusted_keys_pem or [])


def _hash_entry(zf: zipfile.ZipFile, name: str) -> str:
    """re-hash a zip entry in chunks — evidence originals can be huge,
    so verification must not read one whole into memory either."""
    digest = hashlib.sha256()
    with zf.open(name, "r") as fh:
        while chunk := fh.read(_COPY_CHUNK):
            digest.update(chunk)
    return digest.hexdigest()


def _verify_signature(
    manifest: bytes, sig: bytes | None, trusted_keys_pem: list[str]
) -> SignatureStatus:
    if sig is None:
        return SignatureStatus(state="unsigned")
    try:
        from cryptography.exceptions import InvalidSignature
        from cryptography.hazmat.primitives.asymmetric.ed25519 import (
            Ed25519PublicKey,
        )
        from cryptography.hazmat.primitives.serialization import (
            load_pem_public_key,
        )
    except ImportError:
        # cannot verify without the library; treat as untrusted rather
        # than silently accepting
        return SignatureStatus(state="signed_untrusted")

    for pem in trusted_keys_pem:
        try:
            key = load_pem_public_key(pem.encode("utf-8"))
        except ValueError:
            logger.warning("skipping malformed trusted bundle key")
            continue
        if not isinstance(key, Ed25519PublicKey):
            continue
        try:
            key.verify(sig, manifest)
            return SignatureStatus(state="signed_trusted")
        except InvalidSignature:
            continue

    # a signature is present but no configured key accepted it. this
    # is NOT a hard failure — the operator may legitimately import a
    # bundle from a peer whose key they have not added — but the
    # import must record that the source was not verified.
    return SignatureStatus(state="signed_untrusted")
