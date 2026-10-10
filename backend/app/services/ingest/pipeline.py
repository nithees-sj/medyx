"""The ingest pipeline and its in-process background worker.

Stages (shown live in the UI through documents.stage):
Uploading → Reading document → Extracting with AI → Normalising codes & units →
Merging with existing record → Saving to FHIR → Running safety checks → Done
"""

import asyncio
import logging
import uuid
from collections import defaultdict
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

import pymupdf
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import SessionLocal
from app.models import Document, ExtractionItem, HealthProfile, User
from app.services import record as record_service
from app.services.fhir_client import FhirError
from app.services.ingest import normalize as nz
from app.services.ingest.extract import ExtractionFailed, extract_document
from app.services.ingest.merge import Planned, plan
from app.services.ingest.schemas import ExtractionResult
from app.services.ingest.writer import DocumentWrite, write_document

log = logging.getLogger(__name__)

CONFIDENCE_THRESHOLD = 0.80
KINDS = {
    "conditions": "Condition",
    "medications": "MedicationRequest",
    "allergies": "AllergyIntolerance",
    "labs": "Observation",
    "vitals": "Vital",
}

# Hooks run after a successful FHIR write while the profile lock is held (the safety engine registers here).
PostWriteHook = Callable[[AsyncSession, HealthProfile], Awaitable[None]]
post_write_hooks: list[PostWriteHook] = []

_profile_locks: defaultdict[uuid.UUID, asyncio.Lock] = defaultdict(asyncio.Lock)


def profile_lock(profile_id: uuid.UUID) -> asyncio.Lock:
    return _profile_locks[profile_id]


def count_pages(data: bytes, mime: str) -> int:
    if mime != "application/pdf":
        return 1
    with pymupdf.open(stream=data, filetype="pdf") as doc:
        return doc.page_count


async def _stage(db: AsyncSession, doc: Document, stage: str, status: str = "processing") -> None:
    doc.stage = stage
    doc.status = status
    await db.commit()


def needs_review(item: dict[str, Any]) -> bool:
    return float(item.get("confidence", 0)) < CONFIDENCE_THRESHOLD or bool(item.get("uncertain_reason"))


def build_items(doc: Document, result: ExtractionResult) -> list[ExtractionItem]:
    doc_date = nz.parse_date(result.document.document_date)
    out: list[ExtractionItem] = []
    data = result.model_dump()
    for section, kind in KINDS.items():
        for raw in data[section]:
            normalizer = nz.NORMALIZERS[kind]
            normalized = normalizer(raw, doc_date)
            if normalized is None:  # e.g. a vital sign we don't model
                continue
            out.append(
                ExtractionItem(
                    document_id=doc.id,
                    resource_type=kind,
                    payload={"raw": raw, "normalized": normalized},
                    confidence=float(raw.get("confidence", 0)),
                    page=int(raw.get("page") or 1),
                    source_snippet=raw.get("snippet"),
                    review_status="pending" if needs_review(raw) else "auto_accepted",
                )
            )
    return out


async def uploader_agent(db: AsyncSession, doc: Document) -> dict[str, Any]:
    user = await db.get(User, doc.uploaded_by_user_id)
    if user and user.doctor_profile and user.doctor_profile.fhir_practitioner_id:
        return {"reference": f"Practitioner/{user.doctor_profile.fhir_practitioner_id}", "display": user.name}
    return {"display": f"{user.name if user else 'Unknown'} (account owner)"}


async def write_items(
    db: AsyncSession,
    profile: HealthProfile,
    doc: Document,
    items: list[ExtractionItem],
    meta: dict[str, Any],
    existing_docref: str | None = None,
) -> dict[str, int]:
    """Merge + write the given (accepted) items for one document. Caller holds the profile lock."""
    # Another worker may have written since this session loaded the profile.
    await db.refresh(profile)
    record = await record_service.load_record(db, profile)
    planned = plan(
        record,
        [
            Planned(item_id=i.id, kind=i.resource_type, normalized=i.payload["normalized"], raw=i.payload["raw"])
            for i in items
        ],
        meta.get("org_name"),
    )
    data = Path(doc.storage_path).read_bytes()
    docref, refs = await write_document(
        patient_ref=record.patient_ref,
        doc=DocumentWrite(
            doc_id=str(doc.id),
            filename=doc.original_filename,
            mime=doc.mime,
            data=data,
            created_at=doc.created_at,
            document_type=doc.document_type or "other",
            document_date=doc.document_date,
            org_name=meta.get("org_name"),
            org_address=meta.get("org_address"),
            practitioner_name=meta.get("practitioner_name"),
            practitioner_specialty=meta.get("practitioner_specialty"),
            encounter_reason=meta.get("encounter_reason"),
        ),
        planned=planned,
        agent=await uploader_agent(db, doc),
        existing_docref=existing_docref,
    )
    doc.fhir_document_reference_id = docref.split("/")[1]
    for i in items:
        i.fhir_resource_id = refs.get(i.id)
    await bump_record_version(db, profile)
    merged = sum(1 for p in planned if p.existing_ref or p.batch_key is not None)
    return {"merged": merged}


async def bump_record_version(db: AsyncSession, profile: HealthProfile) -> None:
    """Atomic increment (concurrent writers must never lose a version bump)."""
    await db.execute(
        update(HealthProfile)
        .where(HealthProfile.id == profile.id)
        .values(record_version=HealthProfile.record_version + 1)
    )
    await db.flush()
    await db.refresh(profile)
    record_service.invalidate(profile.id)


def _counts(items: list[ExtractionItem]) -> dict[str, int]:
    labels = {"Condition": "conditions", "MedicationRequest": "medications", "AllergyIntolerance": "allergies"}
    counts: dict[str, int] = defaultdict(int)
    for i in items:
        if i.review_status == "rejected":
            continue
        counts[labels.get(i.resource_type, "labs" if i.resource_type == "Observation" else "vitals")] += 1
        if i.review_status == "pending":
            counts["pending"] += 1
    return dict(counts)


async def process_document(doc_id: uuid.UUID) -> None:
    async with SessionLocal() as db:
        doc = await db.get(Document, doc_id)
        if doc is None:
            return
        profile = await db.get(HealthProfile, doc.profile_id)
        assert profile is not None
        try:
            await _stage(db, doc, "Reading document")
            data = Path(doc.storage_path).read_bytes()
            doc.page_count = count_pages(data, doc.mime)

            await _stage(db, doc, "Extracting with AI")
            result, source = await extract_document(data, doc.mime, doc.sha256)

            await _stage(db, doc, "Normalising codes & units")
            info = result.document
            doc.document_type = info.type
            doc.document_date = nz.parse_date(info.document_date) or doc.document_date
            org = info.source_organization.name.strip() if info.source_organization else None
            doc.source_org_name = org.title() if org and org.isupper() else org
            meta = {
                "org_name": doc.source_org_name,
                "org_address": info.source_organization.address if info.source_organization else None,
                "practitioner_name": info.practitioner.name if info.practitioner else None,
                "practitioner_specialty": info.practitioner.specialty if info.practitioner else None,
                "encounter_reason": info.encounter_reason,
                "extraction_source": source,
            }
            # Re-processing (retry) replaces earlier unwritten items for this document.
            for old in (await db.scalars(select(ExtractionItem).where(ExtractionItem.document_id == doc.id))).all():
                await db.delete(old)
            items = build_items(doc, result)
            db.add_all(items)
            doc.result_counts = {**_counts(items), "meta": meta}
            await db.commit()

            async with profile_lock(profile.id):
                await _stage(db, doc, "Merging with existing record")
                accepted = [i for i in items if i.review_status == "auto_accepted"]
                await _stage(db, doc, "Saving to FHIR")
                stats = await write_items(db, profile, doc, accepted, meta)
                await db.commit()
                if post_write_hooks:
                    await _stage(db, doc, "Running safety checks")
                    for hook in post_write_hooks:
                        await hook(db, profile)

            pending = sum(1 for i in items if i.review_status == "pending")
            doc.result_counts = {**_counts(items), **stats, "meta": meta}
            doc.error = None
            await _stage(db, doc, "Done", "needs_review" if pending else "done")
        except (ExtractionFailed, FhirError) as e:
            await db.rollback()
            doc = await db.get(Document, doc_id)
            assert doc is not None
            doc.error = str(e)
            await _stage(db, doc, "Failed", "failed")
        except Exception:
            log.exception("ingest failed for document %s", doc_id)
            await db.rollback()
            doc = await db.get(Document, doc_id)
            assert doc is not None
            doc.error = "Something went wrong while processing this document. Please retry."
            await _stage(db, doc, "Failed", "failed")


class IngestWorker:
    """A tiny asyncio queue worker (no Celery). Extraction runs in parallel; writes are
    serialised per profile by `profile_lock`."""

    def __init__(self, concurrency: int = 3) -> None:
        self.concurrency = concurrency
        self.queue: asyncio.Queue[uuid.UUID] = asyncio.Queue()
        self.tasks: list[asyncio.Task] = []

    def enqueue(self, doc_id: uuid.UUID) -> None:
        self.queue.put_nowait(doc_id)

    async def start(self) -> None:
        async with SessionLocal() as db:
            stuck = (
                await db.scalars(
                    select(Document.id)
                    .where(Document.status.in_(["queued", "processing"]))
                    .order_by(Document.created_at)
                )
            ).all()
        for doc_id in stuck:
            self.enqueue(doc_id)
        self.tasks = [asyncio.create_task(self._run(), name=f"ingest-{i}") for i in range(self.concurrency)]

    async def stop(self) -> None:
        for t in self.tasks:
            t.cancel()
        await asyncio.gather(*self.tasks, return_exceptions=True)

    async def _run(self) -> None:
        while True:
            doc_id = await self.queue.get()
            try:
                await process_document(doc_id)
            except Exception:
                log.exception("worker crashed on %s", doc_id)
            finally:
                self.queue.task_done()


worker = IngestWorker()
