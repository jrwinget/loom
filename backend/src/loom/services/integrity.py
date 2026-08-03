import hmac
from datetime import UTC, datetime
from uuid import UUID

from minio.error import S3Error
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from loom.models.asset import Asset
from loom.models.chain_of_custody import ChainOfCustodyEntry
from loom.schemas.integrity import (
    CaseIntegrityResult,
    CustodyEntryResponse,
    IntegrityReportResponse,
    IntegrityResult,
)
from loom.services.hashing import compute_hashes_from_iterator
from loom.services.storage_backends import (
    ORIGINALS_BUCKET,
    StorageBackend,
)


class IntegrityError(Exception):
    """raised when integrity verification fails fatally."""


async def verify_asset_integrity(
    session: AsyncSession,
    storage: StorageBackend,
    asset_id: str,
    actor_id: str,
    ip_address: str | None = None,
) -> IntegrityResult:
    """verify an asset's stored hashes against its file in storage.

    streams the file in chunks to avoid loading into memory.
    records result as a chain of custody entry.
    uses constant-time comparison via hmac.compare_digest.
    """
    # fetch asset record
    result = await session.execute(
        select(Asset).where(Asset.id == UUID(asset_id))
    )
    asset = result.scalar_one_or_none()
    if not asset:
        raise IntegrityError(f"asset {asset_id} not found")

    verified_at = datetime.now(UTC)

    # stream file from storage and compute hashes. both the minio
    # (S3Error) and local (FileNotFoundError) backends can signal a
    # missing object; treat either as a fatal integrity failure.
    try:
        _file_size, chunks = storage.get_object_stream(
            ORIGINALS_BUCKET,
            asset.storage_key,
        )
    except (S3Error, FileNotFoundError) as exc:
        raise IntegrityError(
            f"cannot read {asset.storage_key} from storage: {exc}"
        ) from exc

    computed_sha256, computed_sha512 = compute_hashes_from_iterator(chunks)

    # constant-time comparison
    sha256_match = hmac.compare_digest(asset.sha256_hash, computed_sha256)
    sha512_match = hmac.compare_digest(asset.sha512_hash, computed_sha512)

    passed = sha256_match and sha512_match

    # stamp verification recency on the asset itself so list views
    # and reports can show it without replaying the custody chain
    asset.last_verified_at = verified_at
    asset.last_verification_ok = passed

    # record custody entry
    entry = ChainOfCustodyEntry(
        asset_id=UUID(asset_id),
        action="integrity_verification",
        actor_id=UUID(actor_id),
        detail={
            "result": "pass" if passed else "fail",
            "sha256_match": sha256_match,
            "sha512_match": sha512_match,
            "computed_sha256": computed_sha256,
            "computed_sha512": computed_sha512,
        },
        ip_address=ip_address,
    )
    session.add(entry)
    await session.flush()

    return IntegrityResult(
        asset_id=asset.id,
        filename=asset.original_filename,
        storage_key=asset.storage_key,
        file_size=asset.file_size_bytes,
        stored_sha256=asset.sha256_hash,
        computed_sha256=computed_sha256,
        stored_sha512=asset.sha512_hash,
        computed_sha512=computed_sha512,
        sha256_match=sha256_match,
        sha512_match=sha512_match,
        verified_at=verified_at,
    )


async def verify_case_integrity(
    session: AsyncSession,
    storage: StorageBackend,
    case_id: str,
    actor_id: str,
    ip_address: str | None = None,
) -> CaseIntegrityResult:
    """verify all assets in a case."""
    result = await session.execute(
        select(Asset).where(Asset.case_id == UUID(case_id))
    )
    assets = list(result.scalars().all())

    results: list[IntegrityResult] = []
    passed_count = 0
    failed_count = 0

    for asset in assets:
        try:
            ir = await verify_asset_integrity(
                session,
                storage,
                str(asset.id),
                actor_id,
                ip_address,
            )
            results.append(ir)
            if ir.passed:
                passed_count += 1
            else:
                failed_count += 1
        except IntegrityError:
            # asset unreadable counts as failure
            failed_count += 1

    return CaseIntegrityResult(
        case_id=UUID(case_id),
        total_assets=len(assets),
        verified_count=len(results),
        passed_count=passed_count,
        failed_count=failed_count,
        results=results,
    )


async def generate_integrity_report(
    session: AsyncSession,
    asset_id: str,
) -> IntegrityReportResponse:
    """generate a court-ready integrity report from stored state.

    read-only: summarizes the ingest hashes, verification recency,
    and recorded custody chain. it never re-hashes the file or
    writes custody entries -- verification stays on the editor-gated
    verify endpoints.
    """
    result = await session.execute(
        select(Asset).where(Asset.id == UUID(asset_id))
    )
    asset = result.scalar_one_or_none()
    if not asset:
        raise IntegrityError(f"asset {asset_id} not found")

    custody_result = await session.execute(
        select(ChainOfCustodyEntry)
        .where(ChainOfCustodyEntry.asset_id == UUID(asset_id))
        .order_by(ChainOfCustodyEntry.timestamp.asc())
    )
    entries = list(custody_result.scalars().all())

    custody_chain = [
        CustodyEntryResponse(
            id=e.id,
            action=e.action,
            actor_id=e.actor_id,
            detail=e.detail,
            ip_address=e.ip_address,
            timestamp=e.timestamp,
        )
        for e in entries
    ]
    verification_history = [
        c for c in custody_chain if c.action == "integrity_verification"
    ]

    return IntegrityReportResponse(
        asset_id=asset.id,
        case_id=asset.case_id,
        original_filename=asset.original_filename,
        storage_key=asset.storage_key,
        media_type=asset.media_type,
        mime_type=asset.mime_type,
        file_size_bytes=asset.file_size_bytes,
        uploaded_by=asset.uploaded_by,
        uploaded_at=asset.uploaded_at,
        sha256_hash=asset.sha256_hash,
        sha512_hash=asset.sha512_hash,
        last_verified_at=asset.last_verified_at,
        last_verification_ok=asset.last_verification_ok,
        verification_history=verification_history,
        custody_chain=custody_chain,
        report_generated_at=datetime.now(UTC),
    )
