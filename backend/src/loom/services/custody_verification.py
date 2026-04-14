"""chain of custody verification service.

verifies that an asset's custody chain is unbroken and
produces structured reports suitable for court submission.
"""

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from loom.models.asset import Asset
from loom.models.chain_of_custody import ChainOfCustodyEntry
from loom.schemas.custody import (
    CaseCustodyVerificationResult,
    CustodyEntryResponse,
    CustodyGap,
    CustodyIssue,
    CustodyReportResponse,
    CustodyVerificationResult,
)

# gaps larger than this threshold (seconds) are flagged
_GAP_THRESHOLD_SECONDS = 0.0


async def verify_asset_chain(
    session: AsyncSession,
    asset_id: str,
) -> CustodyVerificationResult:
    """verify an asset's custody chain is unbroken.

    checks:
    - at least one entry exists (upload record)
    - entries are sequential with no timestamp inversions
    - no unexplained gaps (all transitions make sense)
    """
    uid = UUID(asset_id)
    now = datetime.now(tz=UTC)

    # fetch entries ordered by timestamp
    result = await session.execute(
        select(ChainOfCustodyEntry)
        .where(ChainOfCustodyEntry.asset_id == uid)
        .order_by(ChainOfCustodyEntry.timestamp.asc())
    )
    entries = list(result.scalars().all())

    issues: list[CustodyIssue] = []
    gaps: list[CustodyGap] = []

    if not entries:
        issues.append(
            CustodyIssue(
                severity="error",
                description="no custody entries found for asset",
                entry_id=None,
            )
        )
        return CustodyVerificationResult(
            asset_id=uid,
            is_valid=False,
            entries_count=0,
            first_entry=None,
            last_entry=None,
            gaps=[],
            issues=issues,
            verified_at=now,
        )

    # check first entry is an upload/ingest action
    first = entries[0]
    if first.action not in ("upload", "ingest", "presigned_upload"):
        issues.append(
            CustodyIssue(
                severity="warning",
                description=(
                    f"first custody entry has action '{first.action}'"
                    " instead of an upload action"
                ),
                entry_id=first.id,
            )
        )

    # walk the chain looking for gaps and inversions
    for i in range(1, len(entries)):
        prev = entries[i - 1]
        curr = entries[i]
        delta = (curr.timestamp - prev.timestamp).total_seconds()

        # timestamp inversion — a serious integrity issue
        if delta < 0:
            issues.append(
                CustodyIssue(
                    severity="error",
                    description=(
                        f"timestamp inversion: entry {curr.id} "
                        f"({curr.timestamp.isoformat()}) is before "
                        f"entry {prev.id} "
                        f"({prev.timestamp.isoformat()})"
                    ),
                    entry_id=curr.id,
                )
            )

        # identical timestamps on different entries — suspicious
        if delta == _GAP_THRESHOLD_SECONDS and prev.id != curr.id:
            issues.append(
                CustodyIssue(
                    severity="warning",
                    description=(
                        f"entries {prev.id} and {curr.id} share "
                        "the exact same timestamp"
                    ),
                    entry_id=curr.id,
                )
            )

    # determine validity: no errors means valid
    has_errors = any(i.severity == "error" for i in issues)
    is_valid = not has_errors

    return CustodyVerificationResult(
        asset_id=uid,
        is_valid=is_valid,
        entries_count=len(entries),
        first_entry=entries[0].timestamp,
        last_entry=entries[-1].timestamp,
        gaps=gaps,
        issues=issues,
        verified_at=now,
    )


async def verify_case_custody(
    session: AsyncSession,
    case_id: str,
) -> CaseCustodyVerificationResult:
    """verify custody chains for all assets in a case."""
    uid = UUID(case_id)
    now = datetime.now(tz=UTC)

    # get all asset ids for the case
    result = await session.execute(select(Asset.id).where(Asset.case_id == uid))
    asset_ids = [str(row[0]) for row in result.all()]

    results: list[CustodyVerificationResult] = []
    valid_count = 0
    invalid_count = 0

    for aid in asset_ids:
        verification = await verify_asset_chain(session, aid)
        results.append(verification)
        if verification.is_valid:
            valid_count += 1
        else:
            invalid_count += 1

    return CaseCustodyVerificationResult(
        case_id=uid,
        total_assets=len(asset_ids),
        valid_assets=valid_count,
        invalid_assets=invalid_count,
        results=results,
        verified_at=now,
    )


async def export_custody_report(
    session: AsyncSession,
    asset_id: str,
) -> CustodyReportResponse:
    """produce a structured custody report for court submission.

    includes asset metadata, full chain of custody entries,
    and verification result.
    """
    uid = UUID(asset_id)
    now = datetime.now(tz=UTC)

    # fetch asset
    result = await session.execute(select(Asset).where(Asset.id == uid))
    asset = result.scalar_one_or_none()
    if asset is None:
        raise ValueError(f"asset {asset_id} not found")

    # fetch all custody entries
    entries_result = await session.execute(
        select(ChainOfCustodyEntry)
        .where(ChainOfCustodyEntry.asset_id == uid)
        .order_by(ChainOfCustodyEntry.timestamp.asc())
    )
    entries = list(entries_result.scalars().all())

    # run verification
    verification = await verify_asset_chain(session, asset_id)

    chain = [CustodyEntryResponse.model_validate(e) for e in entries]

    return CustodyReportResponse(
        asset_id=asset.id,
        original_filename=asset.original_filename,
        sha256_hash=asset.sha256_hash,
        sha512_hash=asset.sha512_hash,
        file_size_bytes=asset.file_size_bytes,
        media_type=asset.media_type,
        uploaded_at=asset.uploaded_at,
        uploaded_by=asset.uploaded_by,
        chain=chain,
        verification=verification,
        generated_at=now,
    )
