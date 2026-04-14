import logging
import tempfile
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from loom.models.asset import Asset
from loom.models.chain_of_custody import ChainOfCustodyEntry
from loom.models.export_bundle import ExportBundle
from loom.models.provenance import ProvenanceRecord
from loom.services.storage import (
    DERIVATIVES_BUCKET,
    ORIGINALS_BUCKET,
    StorageService,
)

logger = logging.getLogger(__name__)

CLAIM_GENERATOR = "Loom/0.1.0"

# c2pa-supported mime types for manifest embedding
_C2PA_SUPPORTED_MIMES = frozenset(
    {
        "image/jpeg",
        "image/png",
        "image/webp",
        "image/avif",
        "image/heic",
        "image/heif",
        "video/mp4",
        "audio/mp4",
        "application/mp4",
    }
)


def _c2pa_available() -> bool:
    """check if c2pa-python is installed."""
    try:
        import c2pa  # noqa: F401

        return True
    except ImportError:
        return False


async def build_c2pa_manifest(
    asset_id: str,
    actions: list[dict[str, Any]],
    session: AsyncSession,
) -> dict[str, Any]:
    """build a c2pa-compatible manifest dict for an asset.

    includes claim_generator, asset hash, chain of custody
    actions, and creation timestamp.
    """
    uid = UUID(asset_id)

    # fetch asset
    result = await session.execute(select(Asset).where(Asset.id == uid))
    asset = result.scalar_one_or_none()
    if not asset:
        raise ValueError(f"asset {asset_id} not found")

    # fetch chain of custody entries
    coc_result = await session.execute(
        select(ChainOfCustodyEntry)
        .where(ChainOfCustodyEntry.asset_id == uid)
        .order_by(ChainOfCustodyEntry.timestamp)
    )
    custody_entries = list(coc_result.scalars().all())

    # build c2pa-style actions from custody chain
    c2pa_actions = [
        {
            "action": entry.action,
            "when": entry.timestamp.isoformat(),
            "softwareAgent": CLAIM_GENERATOR,
        }
        for entry in custody_entries
    ]

    # append any additional actions passed in
    for action in actions:
        c2pa_actions.append(
            {
                "action": action.get("action", "unknown"),
                "when": action.get(
                    "when",
                    datetime.now(tz=UTC).isoformat(),
                ),
                "softwareAgent": CLAIM_GENERATOR,
            }
        )

    manifest: dict[str, Any] = {
        "claim_generator": CLAIM_GENERATOR,
        "title": asset.original_filename,
        "format": asset.mime_type,
        "instance_id": str(asset.id),
        "assertions": [
            {
                "label": "c2pa.hash.data",
                "data": {
                    "name": "sha256",
                    "hash": asset.sha256_hash,
                },
            },
            {
                "label": "c2pa.actions",
                "data": {
                    "actions": c2pa_actions,
                },
            },
        ],
        "created_at": datetime.now(tz=UTC).isoformat(),
    }

    return manifest


def sign_manifest(
    manifest: dict[str, Any],
    file_path: str,
    output_path: str,
) -> str | None:
    """attempt to embed a c2pa manifest into a file.

    returns the output path if successful, None if c2pa is
    not installed or the file format is not supported.
    """
    if not _c2pa_available():
        logger.warning("c2pa-python not installed; skipping manifest signing")
        return None

    # check if format is supported
    fmt = manifest.get("format", "")
    if fmt not in _C2PA_SUPPORTED_MIMES:
        logger.warning(
            "file format %s not supported by c2pa; skipping manifest signing",
            fmt,
        )
        return None

    try:
        import c2pa

        # build a c2pa manifest json for the sdk
        manifest_json = {
            "claim_generator": manifest["claim_generator"],
            "title": manifest.get("title", ""),
            "assertions": manifest.get("assertions", []),
        }

        builder = c2pa.Builder(manifest_json)
        builder.sign_file(file_path, output_path)
        return output_path
    except Exception:
        logger.exception("failed to sign c2pa manifest")
        return None


async def create_provenance_record(
    session: AsyncSession,
    asset_id: str | None,
    export_id: str | None,
    manifest: dict[str, Any],
    actions: list[dict[str, Any]],
) -> ProvenanceRecord:
    """store a provenance record in the database."""
    record = ProvenanceRecord(
        asset_id=UUID(asset_id) if asset_id else None,
        export_id=UUID(export_id) if export_id else None,
        manifest_data=manifest,
        claim_generator=CLAIM_GENERATOR,
        actions=actions,
    )
    session.add(record)
    await session.commit()
    await session.refresh(record)
    return record


async def get_asset_provenance(
    session: AsyncSession,
    asset_id: str,
    case_id: str,
) -> list[ProvenanceRecord]:
    """get all provenance records for an asset.

    verifies the asset belongs to the given case.
    """
    # verify asset belongs to case (idor protection)
    asset_result = await session.execute(
        select(Asset).where(
            Asset.id == UUID(asset_id),
            Asset.case_id == UUID(case_id),
        )
    )
    asset = asset_result.scalar_one_or_none()
    if not asset:
        return []

    result = await session.execute(
        select(ProvenanceRecord)
        .where(ProvenanceRecord.asset_id == UUID(asset_id))
        .order_by(ProvenanceRecord.created_at.desc())
    )
    return list(result.scalars().all())


async def get_export_provenance(
    session: AsyncSession,
    export_id: str,
    case_id: str,
) -> list[ProvenanceRecord]:
    """get all provenance records for an export.

    verifies the export belongs to the given case.
    """
    # verify export belongs to case (idor protection)
    export_result = await session.execute(
        select(ExportBundle).where(
            ExportBundle.id == UUID(export_id),
            ExportBundle.case_id == UUID(case_id),
        )
    )
    export = export_result.scalar_one_or_none()
    if not export:
        return []

    result = await session.execute(
        select(ProvenanceRecord)
        .where(ProvenanceRecord.export_id == UUID(export_id))
        .order_by(ProvenanceRecord.created_at.desc())
    )
    return list(result.scalars().all())


async def embed_provenance_in_export(
    session: AsyncSession,
    export_id: str,
    case_id: str,
    storage_service: StorageService,
) -> bool:
    """embed c2pa manifests into each asset of an export.

    for each asset in the export, builds and signs a c2pa
    manifest and stores the signed file. returns True if
    any manifests were embedded.
    """
    if not _c2pa_available():
        logger.warning("c2pa-python not installed; cannot embed provenance")
        return False

    # verify export belongs to case
    export_result = await session.execute(
        select(ExportBundle).where(
            ExportBundle.id == UUID(export_id),
            ExportBundle.case_id == UUID(case_id),
        )
    )
    export = export_result.scalar_one_or_none()
    if not export:
        return False

    # get all assets for this case
    asset_result = await session.execute(
        select(Asset).where(Asset.case_id == UUID(case_id))
    )
    assets = list(asset_result.scalars().all())

    any_embedded = False

    for asset in assets:
        # build manifest
        manifest = await build_c2pa_manifest(
            str(asset.id),
            [{"action": "c2pa.exported", "when": "auto"}],
            session,
        )

        # check if format is supported before downloading
        if asset.mime_type not in _C2PA_SUPPORTED_MIMES:
            # still record the manifest even if we can't embed
            await create_provenance_record(
                session,
                str(asset.id),
                export_id,
                manifest,
                manifest.get("assertions", [{}])[-1]
                .get("data", {})
                .get("actions", []),
            )
            continue

        # download, sign, re-upload
        with (
            tempfile.NamedTemporaryFile(
                suffix=_ext_for_mime(asset.mime_type),
            ) as src,
            tempfile.NamedTemporaryFile(
                suffix=_ext_for_mime(asset.mime_type),
            ) as dst,
        ):
            try:
                storage_service.download_file(
                    ORIGINALS_BUCKET,
                    asset.storage_key,
                    src.name,
                )
                result = sign_manifest(manifest, src.name, dst.name)
                if result:
                    signed_key = (
                        f"exports/{export_id}/"
                        f"provenance/{asset.id}"
                        f"{_ext_for_mime(asset.mime_type)}"
                    )
                    with open(dst.name, "rb") as f:
                        signed_bytes = f.read()
                    storage_service.upload_bytes(
                        DERIVATIVES_BUCKET,
                        signed_key,
                        signed_bytes,
                        asset.mime_type,
                    )
                    any_embedded = True

                    # store record in a savepoint
                    async with session.begin_nested():
                        record = await create_provenance_record(
                            session,
                            str(asset.id),
                            export_id,
                            manifest,
                            manifest.get("assertions", [{}])[-1]
                            .get("data", {})
                            .get("actions", []),
                        )
                        record.manifest_url = signed_key
                    await session.commit()
            except Exception:
                logger.exception(
                    "failed to embed provenance for asset %s",
                    asset.id,
                )
                await session.rollback()

    return any_embedded


def _ext_for_mime(mime_type: str) -> str:
    """return a file extension for a mime type."""
    extensions: dict[str, str] = {
        "image/jpeg": ".jpg",
        "image/png": ".png",
        "image/webp": ".webp",
        "image/avif": ".avif",
        "image/heic": ".heic",
        "image/heif": ".heif",
        "video/mp4": ".mp4",
        "audio/mp4": ".m4a",
        "application/mp4": ".mp4",
    }
    return extensions.get(mime_type, ".bin")
