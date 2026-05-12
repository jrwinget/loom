"""temporal activity for multi-perspective correlation.

thin wrapper around the correlation service: compute
candidate groupings for a case and persist them. the
service layer owns the actual heuristics and replace-on-
re-run semantics for pending candidates.
"""

import logging
import time

from temporalio import activity

from loom.services.correlation import (
    compute_correlation_candidates,
    persist_correlation_candidates,
)
from loom.workflows.shared import get_db_session

logger = logging.getLogger(__name__)


@activity.defn
async def correlate_case_assets(case_id: str) -> int:
    """compute correlation candidates for a case and persist them.

    returns the number of candidates written. idempotent: the
    service layer replaces 'pending' candidates on re-run and
    preserves accepted/rejected ones.
    """
    start = time.monotonic()
    try:
        logger.info("correlating assets for case %s", case_id)

        async with get_db_session() as session:
            try:
                candidates = await compute_correlation_candidates(
                    session,
                    case_id,
                )
            except ValueError:
                # case exceeds MAX_ASSETS_PER_SCAN. logging at warning
                # because the workflow shouldn't retry forever — the
                # case needs operator action to split.
                logger.warning(
                    "skipping correlation for case %s: too many assets",
                    case_id,
                )
                return 0
            persisted = await persist_correlation_candidates(
                session,
                case_id,
                candidates,
            )
            await session.commit()

        count = len(persisted)
        logger.info(
            "persisted %d correlation candidates for case %s",
            count,
            case_id,
        )
        return count
    finally:
        duration = time.monotonic() - start
        logger.debug(
            "correlate_case_assets took %.3fs for case %s",
            duration,
            case_id,
        )
