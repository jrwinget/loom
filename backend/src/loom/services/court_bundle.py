"""build a court-admissible export bundle.

a court bundle is a zip containing:
    cover.pdf             — case name, dates, preparer, bundle sha-256
    declaration.pdf       — pre-filled 28 u.s.c. § 1746 declaration
                            (fre 902(13)/(14)) for counsel to review,
                            complete, and execute
    declaration.txt       — the same declaration as plain text so it
                            stays quotable/editable everywhere
    exhibit_index.pdf     — numbered exhibits (E1..EN) with
                            cross-references to timeline events
    chain_of_custody.json — the custody log for every exhibit
    report.pdf            — timeline + evidence + custody appendix
                            (attorney work product; only when
                            include_analysis is requested)
    exhibits/E###_<name>  — original files, re-verified at export
                            time (only when include_originals)
    verify.html           — standalone in-browser integrity checker
    verify.py             — stdlib-only command-line checker
    VERIFY_README.txt     — plain-language verification instructions
    MANIFEST.sha256       — one line per file: "<sha256>  <path>"
    MANIFEST.sha256.sig   — detached signature (optional)

rendered documents are written as .html instead of .pdf when
weasyprint is not installed — entry names are decided at write
time so an extension never lies about the bytes behind it.

the bundle is deterministic enough to hand to opposing counsel:
every byte in every included file is hashed, and the cover
records the bundle-wide hash so tampering can be detected even
after the zip is unpacked. the shipped verifiers let the other
side check that without installing loom.

this module is pure composition — it delegates to
services/report.py for the timeline pdf and to
services/export.py for the per-asset manifest, then adds the
cover + declaration + exhibit index + MANIFEST.sha256.
"""

import hashlib
import json
import logging
import warnings
import zipfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import UUID

from jinja2 import Environment, FileSystemLoader
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from loom import __version__ as loom_version
from loom.models.annotation import Annotation
from loom.models.asset import Asset
from loom.models.case import Case
from loom.models.chain_of_custody import ChainOfCustodyEntry
from loom.models.timeline import (
    TimelineEvent,
    TimelineEventEvidence,
)
from loom.services.portable_bundle import (
    BundleVerificationError,
    stream_evidence_entry,
)
from loom.services.report import render_report_pdf
from loom.services.storage_backends import ORIGINALS_BUCKET, StorageBackend

logger = logging.getLogger(__name__)

_TEMPLATE_DIR = Path(__file__).resolve().parent.parent / "templates"


def _template_env() -> Environment:
    return Environment(
        loader=FileSystemLoader(str(_TEMPLATE_DIR)),
        autoescape=True,
    )


def _format_dt(value: Any) -> str | None:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, str):
        return value
    return None


async def _fetch_exhibits(
    session: AsyncSession,
    cid: UUID,
    asset_ids: list[str] | None,
) -> list[Asset]:
    """assets in stable order (capture_time then filename) so exhibit
    numbering is reproducible across bundle regenerations.
    """
    query = select(Asset).where(Asset.case_id == cid)
    if asset_ids:
        query = query.where(Asset.id.in_([UUID(a) for a in asset_ids]))
    query = query.order_by(
        Asset.capture_time.asc().nulls_last(),
        Asset.original_filename.asc(),
    )
    result = await session.execute(query)
    return list(result.scalars().all())


async def _fetch_events(
    session: AsyncSession,
    cid: UUID,
    options: dict[str, Any],
) -> list[TimelineEvent]:
    query = select(TimelineEvent).where(TimelineEvent.case_id == cid)
    event_ids = options.get("event_ids")
    if event_ids:
        query = query.where(TimelineEvent.id.in_([UUID(e) for e in event_ids]))
    query = query.order_by(TimelineEvent.event_time_start.asc())
    result = await session.execute(query)
    return list(result.scalars().all())


async def _event_exhibit_refs(
    session: AsyncSession,
    event_ids: list[UUID],
    exhibit_by_asset: dict[UUID, int],
) -> dict[UUID, list[int]]:
    """map each event to its exhibit numbers (sorted, deduped)."""
    if not event_ids:
        return {}
    result = await session.execute(
        select(TimelineEventEvidence).where(
            TimelineEventEvidence.event_id.in_(event_ids)
        )
    )
    refs: dict[UUID, set[int]] = {}
    for link in result.scalars().all():
        if link.asset_id is None:
            continue
        number = exhibit_by_asset.get(link.asset_id)
        if number is None:
            continue
        refs.setdefault(link.event_id, set()).add(number)
    return {eid: sorted(nums) for eid, nums in refs.items()}


async def build_court_bundle_data(
    session: AsyncSession,
    case_id: str,
    options: dict[str, Any],
    *,
    preparer: str | None = None,
) -> dict[str, Any]:
    """gather all data the court-bundle templates need.

    the returned dict is separately consumable for report.html
    (timeline + custody appendix), cover.html, and
    exhibit_index.html. stable exhibit numbering is computed
    here once so all three renderings agree.
    """
    cid = UUID(case_id)

    case_result = await session.execute(select(Case).where(Case.id == cid))
    case = case_result.scalar_one_or_none()
    case_info = {
        "name": case.name if case else "Unknown Case",
        "description": case.description if case else None,
        "status": case.status if case else "unknown",
    }

    exhibits = await _fetch_exhibits(session, cid, options.get("asset_ids"))
    exhibit_by_asset: dict[UUID, int] = {
        a.id: i + 1 for i, a in enumerate(exhibits)
    }

    events = await _fetch_events(session, cid, options)
    event_refs = await _event_exhibit_refs(
        session,
        [e.id for e in events],
        exhibit_by_asset,
    )

    # chain of custody for every included asset, sorted
    # chronologically so the appendix reads as a single timeline
    custody: list[dict[str, Any]] = []
    asset_id_list = list(exhibit_by_asset.keys())
    if asset_id_list:
        coc_q = (
            select(ChainOfCustodyEntry)
            .where(ChainOfCustodyEntry.asset_id.in_(asset_id_list))
            .order_by(ChainOfCustodyEntry.timestamp.asc())
        )
        coc_result = await session.execute(coc_q)
        custody = [
            {
                "asset_id": str(c.asset_id),
                "exhibit_number": exhibit_by_asset.get(c.asset_id),
                "action": c.action,
                "actor_id": str(c.actor_id),
                "timestamp": c.timestamp.isoformat(),
                "detail": c.detail,
            }
            for c in coc_result.scalars().all()
        ]

    # annotations kept for report.html parity
    ann_result = await session.execute(
        select(Annotation).where(Annotation.case_id == cid)
    )
    annotations = [
        {
            "id": str(a.id),
            "type": a.type,
            "content": a.content,
            "asset_id": (str(a.asset_id) if a.asset_id else None),
        }
        for a in ann_result.scalars().all()
    ]

    # build the event list in the shape the existing report
    # template expects, so we can reuse services/report.py's
    # renderer without forking it.
    event_data: list[dict[str, Any]] = []
    for event in events:
        event_data.append(
            {
                "id": str(event.id),
                "title": event.title,
                "description": event.description,
                "event_time_start": event.event_time_start,
                "event_time_end": event.event_time_end,
                "status": event.status,
                "location_description": event.location_description,
                # cross-reference exhibits by number for the index
                "exhibit_numbers": event_refs.get(event.id, []),
                # relationship breakdown deliberately omitted — the
                # main report.html already renders these; the court
                # bundle exhibit index only needs the flat numbers.
                "supporting": [],
                "contradicting": [],
                "context": [],
            }
        )

    exhibit_rows = [
        {
            "number": i + 1,
            "id": str(a.id),
            "original_filename": a.original_filename,
            "media_type": a.media_type,
            "file_size_bytes": a.file_size_bytes,
            "sha256_hash": a.sha256_hash,
            "capture_time": _format_dt(a.capture_time),
        }
        for i, a in enumerate(exhibits)
    ]

    generated_at = datetime.now(UTC)

    return {
        "case": case_info,
        "events": event_data,
        "annotations": annotations,
        "chain_of_custody": custody,
        "exhibits": exhibit_rows,
        "preparer": preparer or "Unknown",
        "generated_at": generated_at.isoformat(),
        "date_range_start": _format_dt(options.get("date_range_start")),
        "date_range_end": _format_dt(options.get("date_range_end")),
    }


def render_cover(
    data: dict[str, Any],
    bundle_sha256: str,
) -> tuple[bytes, bool]:
    """render the cover page.

    bundle_sha256 is the attestation hash over the manifest of
    every other file, so the cover is rendered last, once all
    other entries are known.
    """
    template = _template_env().get_template("cover.html")
    html = template.render(**data, bundle_sha256=bundle_sha256)
    return _html_to_pdf_or_fallback(html)


def render_exhibit_index(data: dict[str, Any]) -> tuple[bytes, bool]:
    """render the numbered-exhibit index."""
    template = _template_env().get_template("exhibit_index.html")
    html = template.render(**data)
    return _html_to_pdf_or_fallback(html)


def _html_to_pdf_or_fallback(html: str) -> tuple[bytes, bool]:
    """pdf-via-weasyprint with html fallback for dev without extras.

    returns (body, is_pdf). when weasyprint is not installed
    (default dev setup) the body is the utf-8 html itself and
    is_pdf is False, so callers can name the bundle entry after
    what the bytes actually are. production installs the
    `report` extra and gets real pdf output.
    """
    try:
        return render_report_pdf(html), True
    except ImportError:
        warnings.warn(
            "weasyprint not installed; court-bundle documents fall "
            "back to html",
            stacklevel=2,
        )
        return html.encode("utf-8"), False


def _doc_entry(stem: str, rendered: tuple[bytes, bool]) -> tuple[str, bytes]:
    """bundle entry (name, body) named for what the bytes are."""
    body, is_pdf = rendered
    return f"{stem}.{'pdf' if is_pdf else 'html'}", body


_DECLARATION_TITLE = (
    "Declaration of Authenticity of Electronic Evidence "
    "(28 U.S.C. § 1746; FRE 902(13)/(14))"
)

_DECLARATION_JURAT = (
    "I declare under penalty of perjury that the foregoing is true and correct."
)

_DECLARATION_COUNSEL_NOTE = (
    "Note to counsel: this declaration was generated by the system "
    "as a draft. Review every statement, complete the declarant "
    "information, and execute before service or filing."
)


def _declaration_statements() -> list[str]:
    """the pre-filled factual statements of the declaration.

    shared by the html and plain-text renderings so the two can
    never drift apart. the custody-scope language deliberately
    claims integrity within this system since ingest and nothing
    earlier — a scene-to-court custody claim would overreach and
    be used against counsel.
    """
    return [
        (
            "The exhibits listed below were exported from Loom "
            f"version {loom_version} (“the system”), an "
            "evidence-management application."
        ),
        (
            "Each file was hashed with SHA-256 at the time it was "
            "ingested into the system. Original files are stored "
            "read-only within the system. Every action affecting a "
            "file is recorded in an append-only chain-of-custody "
            "log; the log covering the exhibits below is included "
            "in this production as chain_of_custody.json."
        ),
        (
            "Where an original file is included in this production, "
            "the system re-read the file in full at export time and "
            "re-verified its SHA-256 hash against the hash recorded "
            "at ingest. The result and time of that verification "
            "are shown for each exhibit below."
        ),
        (
            "Each exhibit has remained within this system since "
            "ingest on the date shown below. This declaration "
            "addresses the integrity of each file from its ingest "
            "into the system through export only; it makes no "
            "representation about the creation of any file or its "
            "handling before ingest into the system."
        ),
    ]


def _declaration_rows(
    data: dict[str, Any],
    exported: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """per-exhibit facts for the declaration table.

    ingest date is the earliest custody entry for the exhibit;
    export-time verification comes from the exported list built
    while streaming originals into the zip.
    """
    ingested: dict[int, str] = {}
    for entry in data["chain_of_custody"]:
        number = entry.get("exhibit_number")
        if number is None:
            continue
        timestamp = entry["timestamp"]
        if number not in ingested or timestamp < ingested[number]:
            ingested[number] = timestamp

    verified_at = {
        item["exhibit_number"]: item["verified_at"]
        for item in exported
        if "exhibit_number" in item
    }

    return [
        {
            "number": ex["number"],
            "filename": ex["original_filename"],
            "sha256": ex["sha256_hash"],
            "ingested": ingested.get(ex["number"]),
            "verified_at": verified_at.get(ex["number"]),
        }
        for ex in data["exhibits"]
    ]


def render_declaration(
    data: dict[str, Any],
    exported: list[dict[str, Any]],
) -> tuple[bytes, bool]:
    """render the § 1746 declaration document."""
    template = _template_env().get_template("declaration.html")
    html = template.render(
        **data,
        title=_DECLARATION_TITLE,
        statements=_declaration_statements(),
        rows=_declaration_rows(data, exported),
        jurat=_DECLARATION_JURAT,
        counsel_note=_DECLARATION_COUNSEL_NOTE,
    )
    return _html_to_pdf_or_fallback(html)


def render_declaration_text(
    data: dict[str, Any],
    exported: list[dict[str, Any]],
) -> str:
    """plain-text rendering of the same declaration so counsel can
    quote or edit it regardless of pdf tooling."""
    lines = [
        _DECLARATION_TITLE,
        "",
        f"Case: {data['case']['name']}",
        f"Prepared by: {data['preparer']}",
        f"Generated: {data['generated_at']}",
        "",
    ]
    for i, statement in enumerate(_declaration_statements(), start=1):
        lines.append(f"{i}. {statement}")
        lines.append("")

    lines.append("Exhibits:")
    lines.append("")
    for row in _declaration_rows(data, exported):
        lines.append(f"  Exhibit E{row['number']}: {row['filename']}")
        lines.append(f"    SHA-256 at intake: {row['sha256']}")
        lines.append(
            "    Within this system since ingest on: "
            f"{row['ingested'] or 'see chain_of_custody.json'}"
        )
        if row["verified_at"]:
            lines.append(
                f"    Export-time check: verified at {row['verified_at']}"
            )
        else:
            lines.append(
                "    Export-time check: original not included in "
                "this production; not re-verified at export"
            )
        lines.append("")

    lines += [
        "Declarant name:  ________________________________",
        "Title / role:    ________________________________",
        "",
        _DECLARATION_JURAT,
        "",
        "Executed on: ____________________",
        "Signature:   ________________________________",
        "",
        _DECLARATION_COUNSEL_NOTE,
        "",
    ]
    return "\n".join(lines)


def _render_manifest_lines(entries: dict[str, str]) -> str:
    """MANIFEST.sha256 body: '<sha256>  <path>' lines, sorted."""
    lines = [f"{entries[path]}  {path}" for path in sorted(entries)]
    return "\n".join(lines) + "\n"


def _sign_manifest(manifest: str, signing_key_pem: str | None) -> bytes | None:
    """sign MANIFEST.sha256 with an Ed25519 key if configured.

    returns the raw signature bytes (base64-free — consumers
    verify via `openssl pkeyutl -verify`) or None if no key is
    provided. absence is not an error; detached signatures are
    an optional admissibility hardening per the issue spec.
    """
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
        logger.warning("cryptography not installed; skipping bundle signature")
        return None

    key = load_pem_private_key(
        signing_key_pem.encode("utf-8"),
        password=None,
    )
    if not isinstance(key, Ed25519PrivateKey):
        logger.warning(
            "bundle_signing_key is not Ed25519 (%s); skipping signature",
            type(key).__name__,
        )
        return None
    sig: bytes = key.sign(manifest.encode("utf-8"))
    return sig


async def build_court_bundle(
    session: AsyncSession,
    case_id: str,
    options: dict[str, Any],
    storage: StorageBackend,
    dest_path: Path,
    *,
    preparer: str | None = None,
    signing_key_pem: str | None = None,
) -> tuple[str, list[dict[str, Any]]]:
    """write the court bundle zip to dest_path.

    returns (bundle_sha256, exported) where exported lists the
    assets whose originals were streamed in and re-verified. the
    caller moves dest_path into storage so bundles with originals
    never live in memory.

    the work-product firewall: report.pdf (the timeline narrative —
    core attorney work product) ships only when include_analysis is
    true; the default court bundle is an evidence-only production
    of cover, exhibit index, custody log, manifest, and optionally
    the original files.
    """
    # import report renderer lazily — the module does db work on
    # import (templates env with autoescape) but not fetches.
    from loom.services.report import (
        build_report_data,
        render_report_html,
    )

    include_analysis = options.get("include_analysis", False)
    include_originals = options.get("include_originals", False)

    data = await build_court_bundle_data(
        session,
        case_id,
        options,
        preparer=preparer,
    )

    listed_files: dict[str, bytes] = {
        # the custody log is evidence-layer and machine-checkable;
        # it ships in every court bundle
        "chain_of_custody.json": json.dumps(
            data["chain_of_custody"], indent=2, sort_keys=True
        ).encode("utf-8"),
        # standalone verifiers so opposing counsel and chambers can
        # check the manifest without installing loom
        "verify.html": (_TEMPLATE_DIR / "verify.html").read_bytes(),
        "verify.py": (_TEMPLATE_DIR / "verify.py").read_bytes(),
        "VERIFY_README.txt": (_TEMPLATE_DIR / "VERIFY_README.txt").read_bytes(),
    }
    index_name, index_body = _doc_entry(
        "exhibit_index", render_exhibit_index(data)
    )
    listed_files[index_name] = index_body

    if include_analysis:
        # reuse the main report renderer with include_custody=True
        # so the timeline pdf includes the custody appendix the
        # issue spec calls for.
        report_data = await build_report_data(
            session,
            case_id,
            {**options, "include_custody": True},
        )
        report_data["work_product"] = True
        report_name, report_body = _doc_entry(
            "report",
            _html_to_pdf_or_fallback(render_report_html(report_data)),
        )
        listed_files[report_name] = report_body

    exported: list[dict[str, Any]] = []
    with zipfile.ZipFile(
        dest_path, "w", compression=zipfile.ZIP_DEFLATED
    ) as zf:
        entries: dict[str, str] = {}

        if include_originals:
            exhibits = await _fetch_exhibits(
                session, UUID(case_id), options.get("asset_ids")
            )
            for number, asset in enumerate(exhibits, start=1):
                entry_name = f"exhibits/E{number:03d}_{asset.original_filename}"
                _size, stream = storage.get_object_stream(
                    ORIGINALS_BUCKET, asset.storage_key
                )
                digest = stream_evidence_entry(zf, entry_name, stream)
                if digest != asset.sha256_hash:
                    raise BundleVerificationError(
                        f"stored bytes for {asset.id} do not match the "
                        "recorded sha256 — refusing to export a corrupt "
                        "original"
                    )
                entries[entry_name] = digest
                exported.append(
                    {
                        "id": str(asset.id),
                        "sha256": digest,
                        "exhibit_number": number,
                        "verified_at": datetime.now(UTC).isoformat(),
                    }
                )

        # the declaration renders after originals stream so it can
        # attest to the export-time re-verification of each one
        decl_name, decl_body = _doc_entry(
            "declaration", render_declaration(data, exported)
        )
        listed_files[decl_name] = decl_body
        listed_files["declaration.txt"] = render_declaration_text(
            data, exported
        ).encode("utf-8")

        # cover carries the bundle-attestation hash: the sha256 of
        # the MANIFEST.sha256 content that lists every other file.
        # that makes the cover self-consistent once written — any
        # later change to a listed file invalidates the attestation.
        #
        # MANIFEST.sha256 follows the standard `sha256sum` convention
        # and does NOT list itself — self-hashing is circular. cover
        # attestation is computed over the manifest bytes instead.
        pre_entries = dict(entries)
        for path, body in listed_files.items():
            pre_entries[path] = hashlib.sha256(body).hexdigest()
        pre_manifest = _render_manifest_lines(pre_entries)
        attest_hash = hashlib.sha256(pre_manifest.encode("utf-8")).hexdigest()

        cover_name, cover_body = _doc_entry(
            "cover", render_cover(data, bundle_sha256=attest_hash)
        )
        listed_files[cover_name] = cover_body

        for path in sorted(listed_files):
            body = listed_files[path]
            zf.writestr(path, body)
            entries[path] = hashlib.sha256(body).hexdigest()

        manifest = _render_manifest_lines(entries)
        zf.writestr("MANIFEST.sha256", manifest.encode("utf-8"))

        signature = _sign_manifest(manifest, signing_key_pem)
        if signature is not None:
            zf.writestr("MANIFEST.sha256.sig", signature)

    bundle_digest = hashlib.sha256()
    with dest_path.open("rb") as fh:
        while chunk := fh.read(1024 * 1024):
            bundle_digest.update(chunk)
    return bundle_digest.hexdigest(), exported
