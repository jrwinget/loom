"""pure logic for lite-profile storage relocation (issue #47).

this module is the backend for the Settings -> Storage page: it
reports disk usage, probes whether a user-picked path is suitable,
computes the "proceed / warning" advisory shown before an ingest
batch, and drives the data-directory relocation wizard with a
verified re-hash on every copy.

the relocation runs as a background asyncio task so the HTTP
request returns 202 immediately; progress is polled via
``RelocationJob`` entries held in the module-level registry.
single-process Lite deploys tolerate an in-memory registry;
restarting the Tauri shell mid-relocation simply surfaces an
"unknown job" (the partial copy on disk is safe — sources are
never touched until the destination hash matches).
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import os
import shutil
import sys
from collections.abc import Callable
from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from loom.models.chain_of_custody import ChainOfCustodyEntry
from loom.services.storage_backends.base import (
    DERIVATIVES_BUCKET,
    ORIGINALS_BUCKET,
)

logger = logging.getLogger(__name__)

# advisory thresholds. in bytes.
_SYSTEM_DRIVE_SMALL_THRESHOLD = 10 * 1024**3
_SYSTEM_DRIVE_LARGE_THRESHOLD = 50 * 1024**3
_SMALL_DRIVE_CUTOFF = 512 * 1024**3

# tokens that signal a cloud-sync mount; reject these outright so a
# copy doesn't get mangled by a third-party sync client that rewrites
# file times or applies its own quarantine.
_CLOUD_SYNC_TOKENS = ("icloud", "onedrive", "google drive", "dropbox")

# 1 MiB streaming chunk for sha-256. sized to amortize syscall
# overhead without dominating working set on low-memory laptops.
_HASH_CHUNK_BYTES = 1024 * 1024

_BUCKETS_DIRNAME = "buckets"
_LOGS_DIRNAME = "logs"
_DB_FILENAME = "loom.db"


# ---------------------------------------------------------------------
# usage + path probes
# ---------------------------------------------------------------------


def _dir_size(path: Path) -> int:
    """sum of file sizes under ``path``; 0 when missing."""
    if not path.exists():
        return 0
    total = 0
    for entry in path.rglob("*"):
        try:
            if entry.is_file():
                total += entry.stat().st_size
        except OSError:
            # stat can race with deletion or hit a permission wall —
            # skip unreadable entries rather than abort the walk.
            continue
    return total


def _is_on_system_drive(path: Path) -> bool:
    """true when ``path`` lives on the same drive as the OS.

    on posix we compare st_dev ids between the path and the user's
    home directory; on windows we compare the resolved drive letter
    with %SYSTEMDRIVE%. any detection error defaults to True so the
    advisory trips — the failure mode is "warn the user" not "let
    them fill the boot drive".
    """
    try:
        if sys.platform == "win32":
            system_drive = os.environ.get("SYSTEMDRIVE", "C:").upper()
            resolved = str(path.resolve())
            drive = os.path.splitdrive(resolved)[0].upper()
            return drive == system_drive
        # posix: compare device ids; home() is the best proxy for
        # "the drive the OS was installed on" without parsing mounts.
        probe = path if path.exists() else path.parent
        if not probe.exists():
            probe = Path.home()
        return probe.stat().st_dev == Path.home().stat().st_dev
    except OSError:
        return True


def get_storage_usage(data_dir: Path) -> dict[str, int | str | bool]:
    """report free/total bytes + per-subdir breakdown under data_dir."""
    resolved = data_dir.expanduser().resolve()
    usage = shutil.disk_usage(
        resolved if resolved.exists() else resolved.parent
    )
    buckets = resolved / _BUCKETS_DIRNAME
    originals = _dir_size(buckets / ORIGINALS_BUCKET)
    derivatives = _dir_size(buckets / DERIVATIVES_BUCKET)
    logs = _dir_size(resolved / _LOGS_DIRNAME)
    db_path = resolved / _DB_FILENAME
    db = db_path.stat().st_size if db_path.exists() else 0

    return {
        "data_dir": str(resolved),
        "free_bytes": int(usage.free),
        "total_bytes": int(usage.total),
        "originals_bytes": originals,
        "derivatives_bytes": derivatives,
        "db_bytes": db,
        "logs_bytes": logs,
        "on_system_drive": _is_on_system_drive(resolved),
    }


def probe_path_writable(path: Path) -> tuple[bool, str | None]:
    """try creating ``path`` and writing a probe file there."""
    resolved_str = str(path.expanduser().resolve()).lower()
    for token in _CLOUD_SYNC_TOKENS:
        if token in resolved_str:
            return (
                False,
                f"path appears to live inside a cloud-sync folder "
                f"({token!r}); Loom needs a local or external drive "
                "to preserve hashes and file times.",
            )
    try:
        resolved = path.expanduser().resolve()
        resolved.mkdir(parents=True, exist_ok=True)
        probe = resolved / ".loom-write-probe"
        probe.write_bytes(b"ok")
        probe.unlink()
    except OSError as err:
        return False, f"cannot write to {path}: {err}"
    return True, None


def compute_advisory(
    free_bytes: int,
    total_bytes: int,
    estimated_batch_size: int,
    on_system_drive: bool,
) -> tuple[str, str | None]:
    """classify an ingest batch as proceed / warning.

    the "blocked" verdict is reserved for callers that have already
    determined the path isn't writable; this function only grades
    free-space pressure against the planned batch.
    """
    if estimated_batch_size > free_bytes * 0.5:
        return (
            "warning",
            "planned batch would consume more than half of free "
            f"space ({estimated_batch_size} bytes vs "
            f"{free_bytes} bytes free).",
        )
    if on_system_drive:
        threshold = (
            _SYSTEM_DRIVE_SMALL_THRESHOLD
            if total_bytes <= _SMALL_DRIVE_CUTOFF
            else _SYSTEM_DRIVE_LARGE_THRESHOLD
        )
        if estimated_batch_size > threshold:
            return (
                "warning",
                f"ingesting {estimated_batch_size} bytes onto the "
                "system drive — consider an external disk so a full "
                "data dir can't brick the OS.",
            )
    return "proceed", None


# ---------------------------------------------------------------------
# relocation job state
# ---------------------------------------------------------------------


@dataclass
class RelocationJob:
    """tracking envelope for a running data-dir relocation."""

    job_id: str
    src: Path
    dst: Path
    status: str = "running"
    assets_copied: int = 0
    assets_total: int = 0
    bytes_copied: int = 0
    bytes_total: int = 0
    error: str | None = None
    started_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    completed_at: datetime | None = None
    # retained so the event loop can't GC the background task; not
    # part of the api response (see RelocationJobStatus schema).
    task: asyncio.Task[None] | None = None


# single-process lite deploys keep the registry in memory; a restart
# abandons the job but leaves sources intact (see module docstring).
RELOCATION_REGISTRY: dict[str, RelocationJob] = {}


SessionFactory = Callable[[], AbstractAsyncContextManager[AsyncSession]]


# ---------------------------------------------------------------------
# hashing helper
# ---------------------------------------------------------------------


def _hash_file(path: Path) -> str:
    """streaming sha-256 of ``path`` in 1mib chunks."""
    hasher = hashlib.sha256()
    with path.open("rb") as fh:
        while True:
            chunk = fh.read(_HASH_CHUNK_BYTES)
            if not chunk:
                break
            hasher.update(chunk)
    return hasher.hexdigest()


# ---------------------------------------------------------------------
# relocation driver
# ---------------------------------------------------------------------


def _asset_id_from_key(rel_parts: tuple[str, ...]) -> UUID | None:
    """extract the asset id from a storage key under a bucket.

    storage keys are ``{case_id}/{asset_id}/{filename}`` (see
    ``services.ingest.generate_storage_key``) so the asset id is the
    second path segment. returns None for keys that don't match the
    expected shape — those paths are still copied + verified, but
    without a custody entry since no asset row owns them.
    """
    if len(rel_parts) < 2:
        return None
    try:
        return UUID(rel_parts[1])
    except ValueError:
        return None


def _iter_bucket_files(buckets_root: Path) -> list[tuple[Path, Path]]:
    """yield (absolute_source, relative_path_under_buckets) tuples."""
    out: list[tuple[Path, Path]] = []
    if not buckets_root.exists():
        return out
    for bucket in (ORIGINALS_BUCKET, DERIVATIVES_BUCKET):
        bucket_root = buckets_root / bucket
        if not bucket_root.exists():
            continue
        for entry in bucket_root.rglob("*"):
            if entry.is_file():
                rel = entry.relative_to(buckets_root)
                out.append((entry, rel))
    return out


def _copy_non_bucket_tree(
    src_root: Path,
    dst_root: Path,
    subdir: str,
) -> None:
    """mirror ``src_root/subdir`` into ``dst_root/subdir``.

    used for ``logs/`` — these are not evidentiary assets so no
    per-file custody entry is required. the db file is copied
    separately because it's a single file rather than a tree.
    """
    src = src_root / subdir
    dst = dst_root / subdir
    if not src.exists():
        return
    dst.mkdir(parents=True, exist_ok=True)
    for entry in src.rglob("*"):
        rel = entry.relative_to(src)
        target = dst / rel
        if entry.is_dir():
            target.mkdir(parents=True, exist_ok=True)
        elif entry.is_file():
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(entry, target)


def _active_job() -> RelocationJob | None:
    for job in RELOCATION_REGISTRY.values():
        if job.status == "running":
            return job
    return None


def start_relocation(
    session_factory: SessionFactory,
    src: Path,
    dst: Path,
    user_id: UUID,
) -> RelocationJob:
    """validate inputs and spawn the background relocation task."""
    src_resolved = src.expanduser().resolve()
    dst_resolved = dst.expanduser().resolve()

    if not src_resolved.exists():
        raise ValueError(f"source data dir does not exist: {src_resolved}")
    writable, reason = probe_path_writable(dst_resolved)
    if not writable:
        raise ValueError(reason or f"destination not writable: {dst_resolved}")
    # no circular relocation: dst must not be inside src. use
    # is_relative_to so a sibling path at the same depth is fine.
    try:
        if dst_resolved.is_relative_to(src_resolved):
            raise ValueError(
                "destination path is inside the current data dir; "
                "choose a path on a different drive or parent."
            )
    except AttributeError:  # pragma: no cover - <3.9 shim, unused.
        raise ValueError(
            "destination path is inside the current data dir; "
            "choose a path on a different drive or parent."
        ) from None

    existing = _active_job()
    if existing is not None:
        raise ValueError(
            f"a relocation is already in progress ({existing.job_id})"
        )

    # enumerate source files up front so the job has an accurate
    # denominator — the picker UI uses this for ETA + progress.
    pairs = _iter_bucket_files(src_resolved / _BUCKETS_DIRNAME)
    total_bytes = sum(p.stat().st_size for p, _ in pairs)

    job = RelocationJob(
        job_id=str(uuid4()),
        src=src_resolved,
        dst=dst_resolved,
        assets_total=len(pairs),
        bytes_total=total_bytes,
    )
    RELOCATION_REGISTRY[job.job_id] = job

    # retain the task on the job envelope so the event loop can't GC
    # it before completion and so tests can await it deterministically.
    task = asyncio.create_task(
        _run_relocation(session_factory, job, pairs, user_id)
    )
    job.task = task
    return job


async def _run_relocation(
    session_factory: SessionFactory,
    job: RelocationJob,
    pairs: list[tuple[Path, Path]],
    user_id: UUID,
) -> None:
    """copy every bucket file, verify its hash, record custody.

    runs in its own asyncio task, outside the request lifecycle, so
    it must own its db session (hence ``session_factory`` rather
    than an injected session). on any hash mismatch we delete the
    bad destination copy, mark the job failed, and leave sources
    untouched — evidence never degrades silently.
    """
    loop = asyncio.get_running_loop()
    dst_buckets = job.dst / _BUCKETS_DIRNAME
    dst_buckets.mkdir(parents=True, exist_ok=True)

    try:
        for src_abs, rel in pairs:
            dst_abs = dst_buckets / rel
            dst_abs.parent.mkdir(parents=True, exist_ok=True)

            # run hashing + copy in an executor because streaming
            # sha-256 is cpu-bound and would starve the event loop
            # for the duration of a large video file.
            src_hash = await loop.run_in_executor(None, _hash_file, src_abs)
            await loop.run_in_executor(None, shutil.copy2, src_abs, dst_abs)
            dst_hash = await loop.run_in_executor(None, _hash_file, dst_abs)

            if src_hash != dst_hash:
                # never leave a miscopied file on disk — a partial
                # relocation that looks complete is worse than a
                # loud failure.
                try:
                    dst_abs.unlink(missing_ok=True)
                except OSError:
                    logger.warning("failed to remove bad copy at %s", dst_abs)
                job.status = "failed"
                job.error = (
                    f"hash mismatch on {rel}: src={src_hash} dst={dst_hash}"
                )
                job.completed_at = datetime.now(UTC)
                return

            asset_id = _asset_id_from_key(rel.parts[1:])
            if asset_id is not None:
                async with session_factory() as session:
                    session.add(
                        ChainOfCustodyEntry(
                            asset_id=asset_id,
                            action="data_dir_relocated",
                            actor_id=user_id,
                            detail={
                                "from": str(job.src),
                                "to": str(job.dst),
                                "verified_hash": dst_hash,
                                "relative_path": str(rel),
                            },
                        )
                    )
                    await session.commit()

            job.assets_copied += 1
            job.bytes_copied += src_abs.stat().st_size

        # non-evidentiary auxiliaries — the db file itself and the
        # logs tree. copied after the bucket contents so a mid-run
        # crash leaves a consistent "originals already moved" state.
        db_src = job.src / _DB_FILENAME
        if db_src.exists():
            await loop.run_in_executor(
                None, shutil.copy2, db_src, job.dst / _DB_FILENAME
            )
        await loop.run_in_executor(
            None, _copy_non_bucket_tree, job.src, job.dst, _LOGS_DIRNAME
        )

        job.status = "completed"
        job.completed_at = datetime.now(UTC)
    except Exception as err:  # pragma: no cover - defensive
        logger.exception("relocation job %s failed", job.job_id)
        job.status = "failed"
        job.error = str(err)
        job.completed_at = datetime.now(UTC)
