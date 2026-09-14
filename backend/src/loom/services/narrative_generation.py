"""ai-drafted prose narratives over a case's own custody/audit metadata.

deliberately narrow: the generation step only ever sees typed
chain-of-custody or audit-log rows, never transcript text, ocr text,
annotation content, or any other evidentiary material — there is
nothing here for a model to hallucinate *about* beyond phrasing, since
every factual claim in the output is checkable against the very rows it
summarized. every draft starts inert (``status="draft"``) and only the
dedicated approve/reject endpoints may change that; export-bundle
assembly must only ever include ``status == "approved"`` rows.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from loom.models.asset import Asset
from loom.models.audit import AuditLogEntry
from loom.models.case import Case
from loom.models.chain_of_custody import ChainOfCustodyEntry
from loom.models.narrative_draft import NarrativeDraft
from loom.services.ai_config import load_text_gen_config
from loom.services.audit_viewer import list_audit_entries
from loom.services.text_generation import generate_text

# a generous but bounded window: enough for a real case history, small
# enough to keep the prompt (and therefore the egress payload) bounded.
_MAX_SOURCE_ENTRIES = 200

_SYSTEM_PROMPT = (
    "You are drafting a plain-language custody/activity narrative for a "
    "legal case management tool. You are given a chronological list of "
    "structured log entries (timestamp, actor, action, detail) and "
    "nothing else. Summarize them into a short, factual, chronological "
    "narrative suitable as a first-pass draft for courtroom preparation. "
    "State only what the entries show — never infer intent, never "
    "speculate, and never add information not present in the entries. "
    "This is an unreviewed AI draft; a human will verify it before use."
)


class NarrativeGenerationError(Exception):
    """raised when a narrative can't be generated or reviewed."""


def _custody_line(entry: ChainOfCustodyEntry) -> str:
    detail = f" {entry.detail}" if entry.detail else ""
    ts = entry.timestamp.isoformat()
    return f"{ts} | actor={entry.actor_id} | {entry.action}{detail}"


def _audit_line(entry: AuditLogEntry) -> str:
    detail = f" {entry.detail}" if entry.detail else ""
    actor = entry.actor_id if entry.actor_id else "system"
    ts = entry.timestamp.isoformat()
    return f"{ts} | actor={actor} | {entry.action}{detail}"


async def _custody_source(
    session: AsyncSession, asset_id: str
) -> tuple[list[UUID], list[str]]:
    result = await session.execute(
        select(ChainOfCustodyEntry)
        .where(ChainOfCustodyEntry.asset_id == UUID(asset_id))
        .order_by(ChainOfCustodyEntry.timestamp.asc())
        .limit(_MAX_SOURCE_ENTRIES)
    )
    entries = list(result.scalars().all())
    return [e.id for e in entries], [_custody_line(e) for e in entries]


async def _audit_source(
    session: AsyncSession, case_id: str
) -> tuple[list[UUID], list[str]]:
    entries, _total = await list_audit_entries(
        session, case_id=case_id, skip=0, limit=_MAX_SOURCE_ENTRIES
    )
    # list_audit_entries orders newest-first for the activity feed;
    # a narrative reads better chronologically.
    entries = list(reversed(entries))
    return [e.id for e in entries], [_audit_line(e) for e in entries]


async def generate_narrative(
    session: AsyncSession,
    *,
    case_id: str,
    asset_id: str | None,
    user_id: str,
) -> NarrativeDraft:
    """draft a narrative over a case's audit log, or one asset's chain
    of custody when ``asset_id`` is given.
    """
    case = await session.get(Case, UUID(case_id))
    if case is None:
        raise NarrativeGenerationError("case not found")
    if case.hold_active:
        raise NarrativeGenerationError(
            "case is under litigation hold; narrative generation is disabled"
        )

    config = await load_text_gen_config(session)
    if not config.usable:
        raise NarrativeGenerationError(
            "text generation is not configured for this install"
        )

    if asset_id is not None:
        asset = await session.get(Asset, UUID(asset_id))
        if asset is None or str(asset.case_id) != case_id:
            raise NarrativeGenerationError("asset not found in this case")
        source_ids, lines = await _custody_source(session, asset_id)
    else:
        source_ids, lines = await _audit_source(session, case_id)

    if not lines:
        raise NarrativeGenerationError("no custody/audit entries to summarize")

    result = await generate_text(
        provider=config.provider,
        base_url=config.api_base_url,
        api_key=config.api_key,
        model=config.model,
        system_prompt=_SYSTEM_PROMPT,
        user_prompt="\n".join(lines),
    )

    draft = NarrativeDraft(
        case_id=UUID(case_id),
        asset_id=UUID(asset_id) if asset_id else None,
        status="draft",
        text=result.text,
        source_entry_ids=[str(i) for i in source_ids],
        model_name=f"cloud:{result.model}",
        model_version="api",
        model_params=result.provenance,
        generated_by=UUID(user_id),
    )
    session.add(draft)
    session.add(
        AuditLogEntry(
            actor_id=UUID(user_id),
            action="ai_narrative_generated",
            resource_type="case" if asset_id is None else "asset",
            resource_id=UUID(asset_id) if asset_id else UUID(case_id),
            # hashes/id references only — never the prompt or the
            # generated text itself, since audit detail can be rendered
            # verbatim into a court bundle appendix.
            detail={
                "provider": result.provenance.get("provider"),
                "model": result.model,
                "source_entry_count": len(source_ids),
            },
        )
    )
    await session.commit()
    await session.refresh(draft)
    return draft


async def get_narrative(
    session: AsyncSession, narrative_id: str
) -> NarrativeDraft | None:
    return await session.get(NarrativeDraft, UUID(narrative_id))


async def list_narratives(
    session: AsyncSession,
    case_id: str,
    *,
    asset_id: str | None = None,
) -> list[NarrativeDraft]:
    query = (
        select(NarrativeDraft)
        .where(NarrativeDraft.case_id == UUID(case_id))
        .order_by(NarrativeDraft.created_at.desc())
    )
    if asset_id is not None:
        query = query.where(NarrativeDraft.asset_id == UUID(asset_id))
    result = await session.execute(query)
    return list(result.scalars().all())


async def _review(
    session: AsyncSession,
    narrative: NarrativeDraft,
    *,
    user_id: str,
    decision: str,
) -> NarrativeDraft:
    narrative.status = decision
    narrative.reviewed_by = UUID(user_id)
    narrative.reviewed_at = datetime.now(UTC)
    session.add(
        AuditLogEntry(
            actor_id=UUID(user_id),
            action=f"ai_narrative_{decision}",
            resource_type="narrative_draft",
            resource_id=narrative.id,
            detail={"case_id": str(narrative.case_id)},
        )
    )
    await session.commit()
    await session.refresh(narrative)
    return narrative


async def approve_narrative(
    session: AsyncSession, narrative: NarrativeDraft, *, user_id: str
) -> NarrativeDraft:
    return await _review(
        session, narrative, user_id=user_id, decision="approved"
    )


async def reject_narrative(
    session: AsyncSession, narrative: NarrativeDraft, *, user_id: str
) -> NarrativeDraft:
    return await _review(
        session, narrative, user_id=user_id, decision="rejected"
    )
