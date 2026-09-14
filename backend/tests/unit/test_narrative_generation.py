"""unit tests for ai-drafted custody/audit narrative generation."""

from collections.abc import AsyncIterator
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from loom.models.asset import Asset
from loom.models.audit import AuditLogEntry
from loom.models.base import Base
from loom.models.case import Case
from loom.models.chain_of_custody import ChainOfCustodyEntry
from loom.models.user import User
from loom.services import narrative_generation as narrative_module
from loom.services.ai_config import save_text_gen_config
from loom.services.narrative_generation import (
    NarrativeGenerationError,
    approve_narrative,
    generate_narrative,
    list_narratives,
    reject_narrative,
)
from loom.services.text_generation import TextGenerationResult

_USER_ID = uuid4()
_CASE_ID = uuid4()
_ASSET_ID = uuid4()


@pytest_asyncio.fixture
async def session() -> AsyncIterator[AsyncSession]:
    engine = create_async_engine("sqlite+aiosqlite://")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as s:
        s.add(
            User(
                id=_USER_ID,
                email="ada@example.org",
                display_name="Ada",
                password_hash="x",
            )
        )
        s.add(Case(id=_CASE_ID, name="Test Case", created_by=_USER_ID))
        s.add(
            Asset(
                id=_ASSET_ID,
                case_id=_CASE_ID,
                original_filename="clip.mp4",
                media_type="video",
                mime_type="video/mp4",
                file_size_bytes=10,
                sha256_hash="a" * 64,
                sha512_hash="b" * 128,
                storage_key="k",
                uploaded_by=_USER_ID,
            )
        )
        s.add(
            ChainOfCustodyEntry(
                asset_id=_ASSET_ID,
                action="ingested",
                actor_id=_USER_ID,
                detail={"source": "upload"},
            )
        )
        s.add(
            AuditLogEntry(
                actor_id=_USER_ID,
                action=f"POST /api/v1/cases/{_CASE_ID}/assets/upload-stream",
                resource_type="asset",
                resource_id=_ASSET_ID,
                detail=None,
            )
        )
        await s.commit()
        yield s
    await engine.dispose()


async def _enable_text_gen(session: AsyncSession) -> None:
    await save_text_gen_config(
        session,
        {
            "enabled": True,
            "provider": "oss",
            "api_base_url": "https://my-llm.example.com/v1",
            "model": "my-model",
        },
    )


@pytest.fixture(autouse=True)
def _fake_generate_text(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _fake(*, provider, base_url, api_key, model, **kwargs):
        return TextGenerationResult(
            text="On the given dates, the following custody events occurred.",
            model=model,
            provenance={
                "provider": provider,
                "endpoint": "my-llm.example.com",
                "model": model,
            },
        )

    monkeypatch.setattr(narrative_module, "generate_text", _fake)


async def test_case_wide_narrative_uses_audit_log(
    session: AsyncSession,
) -> None:
    await _enable_text_gen(session)
    draft = await generate_narrative(
        session, case_id=str(_CASE_ID), asset_id=None, user_id=str(_USER_ID)
    )
    assert draft.status == "draft"
    assert draft.asset_id is None
    assert draft.case_id == _CASE_ID
    assert "custody events" in draft.text
    assert draft.source_entry_ids
    assert draft.model_name == "cloud:my-model"


async def test_asset_scoped_narrative_uses_chain_of_custody(
    session: AsyncSession,
) -> None:
    await _enable_text_gen(session)
    draft = await generate_narrative(
        session,
        case_id=str(_CASE_ID),
        asset_id=str(_ASSET_ID),
        user_id=str(_USER_ID),
    )
    assert draft.asset_id == _ASSET_ID


async def test_generation_writes_audit_entry_with_no_prompt_or_text(
    session: AsyncSession,
) -> None:
    await _enable_text_gen(session)
    await generate_narrative(
        session, case_id=str(_CASE_ID), asset_id=None, user_id=str(_USER_ID)
    )
    from sqlalchemy import select

    result = await session.execute(
        select(AuditLogEntry).where(
            AuditLogEntry.action == "ai_narrative_generated"
        )
    )
    entry = result.scalar_one()
    detail_str = str(entry.detail)
    assert "custody events" not in detail_str  # never the generated text
    assert entry.detail["source_entry_count"] > 0


async def test_rejects_when_case_under_litigation_hold(
    session: AsyncSession,
) -> None:
    await _enable_text_gen(session)
    case = await session.get(Case, _CASE_ID)
    assert case is not None
    case.hold_active = True
    await session.commit()

    with pytest.raises(NarrativeGenerationError, match=r"(?i)litigation hold"):
        await generate_narrative(
            session, case_id=str(_CASE_ID), asset_id=None, user_id=str(_USER_ID)
        )


async def test_rejects_when_text_generation_not_configured(
    session: AsyncSession,
) -> None:
    with pytest.raises(NarrativeGenerationError, match=r"(?i)not configured"):
        await generate_narrative(
            session, case_id=str(_CASE_ID), asset_id=None, user_id=str(_USER_ID)
        )


async def test_rejects_unknown_case(session: AsyncSession) -> None:
    await _enable_text_gen(session)
    with pytest.raises(NarrativeGenerationError, match=r"(?i)case not found"):
        await generate_narrative(
            session, case_id=str(uuid4()), asset_id=None, user_id=str(_USER_ID)
        )


async def test_rejects_asset_not_in_case(session: AsyncSession) -> None:
    await _enable_text_gen(session)
    with pytest.raises(NarrativeGenerationError, match=r"(?i)asset not found"):
        await generate_narrative(
            session,
            case_id=str(_CASE_ID),
            asset_id=str(uuid4()),
            user_id=str(_USER_ID),
        )


async def test_approve_sets_status_and_reviewer(session: AsyncSession) -> None:
    await _enable_text_gen(session)
    draft = await generate_narrative(
        session, case_id=str(_CASE_ID), asset_id=None, user_id=str(_USER_ID)
    )
    approved = await approve_narrative(session, draft, user_id=str(_USER_ID))
    assert approved.status == "approved"
    assert approved.reviewed_by == _USER_ID
    assert approved.reviewed_at is not None


async def test_reject_sets_status_and_reviewer(session: AsyncSession) -> None:
    await _enable_text_gen(session)
    draft = await generate_narrative(
        session, case_id=str(_CASE_ID), asset_id=None, user_id=str(_USER_ID)
    )
    rejected = await reject_narrative(session, draft, user_id=str(_USER_ID))
    assert rejected.status == "rejected"
    assert rejected.reviewed_by == _USER_ID


async def test_list_narratives_scopes_by_case_and_asset(
    session: AsyncSession,
) -> None:
    await _enable_text_gen(session)
    await generate_narrative(
        session, case_id=str(_CASE_ID), asset_id=None, user_id=str(_USER_ID)
    )
    await generate_narrative(
        session,
        case_id=str(_CASE_ID),
        asset_id=str(_ASSET_ID),
        user_id=str(_USER_ID),
    )

    all_items = await list_narratives(session, str(_CASE_ID))
    assert len(all_items) == 2

    asset_items = await list_narratives(
        session, str(_CASE_ID), asset_id=str(_ASSET_ID)
    )
    assert len(asset_items) == 1
    assert asset_items[0].asset_id == _ASSET_ID
