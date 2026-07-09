"""temporal activity for the bundle-import sequence.

the endpoint creates the (empty) case synchronously so its id is
known for status polling, stores the verified bundle, and dispatches
this activity to populate it. the activity is self-contained from
the case id alone — it re-downloads and re-verifies the bundle, so a
retry re-derives everything and never trusts state carried across
the boundary.
"""

import json
import logging
import time
import zipfile
from pathlib import Path
from uuid import UUID

from temporalio import activity

from loom.metrics import ingest_workflow_duration
from loom.models.case import Case
from loom.services.bundle_import import recreate_case_contents
from loom.services.portable_bundle import verify_bundle
from loom.services.storage_backends import DERIVATIVES_BUCKET
from loom.services.streaming_upload import upload_tmp_dir
from loom.workflows.shared import get_db_session, get_storage_backend

logger = logging.getLogger(__name__)


def _bundle_key(case_id: str) -> str:
    return f"imports/{case_id}/bundle.zip"


@activity.defn
async def import_bundle(case_id: str) -> str:
    """recreate a case's contents from its stored portable bundle."""
    from loom.config import get_settings

    start = time.monotonic()
    tmp = upload_tmp_dir() / f"import-download-{case_id}.zip"
    try:
        storage = get_storage_backend()
        await _download(storage, _bundle_key(case_id), tmp)

        settings = get_settings()
        # re-verify on the way in: a tampered bundle must not import
        # even if something bypassed the endpoint's synchronous check
        signature = verify_bundle(
            tmp, trusted_keys_pem=settings.bundle_verify_public_keys
        )
        with zipfile.ZipFile(tmp, "r") as zf:
            meta = json.loads(zf.read("bundle.json"))

        async with get_db_session() as session:
            case = await session.get(Case, UUID(case_id))
            if case is None:
                raise ValueError(f"import target case {case_id} not found")
            counts = await recreate_case_contents(
                session,
                case,
                tmp,
                storage,
                importer_id=str(case.created_by),
                signature=signature,
                bundle_sha256=case.source_bundle_sha256 or "",
                source_deploy=str(meta.get("source_deploy", "unknown")),
            )
            await session.commit()

        logger.info("imported case %s: %s", case_id, counts)
        return case_id
    finally:
        tmp.unlink(missing_ok=True)
        ingest_workflow_duration.labels(activity="bundle_import").observe(
            time.monotonic() - start
        )


async def _download(storage: object, key: str, dest: Path) -> None:
    import asyncio

    await asyncio.get_running_loop().run_in_executor(
        None,
        storage.download_file,  # type: ignore[attr-defined]
        DERIVATIVES_BUCKET,
        key,
        str(dest),
    )
