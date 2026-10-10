"""Review queue: low-confidence items wait here until a person confirms, corrects or rejects them."""

import uuid
from datetime import date, datetime
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.deps import client_ip, current_user
from app.models import Document, ExtractionItem, HealthProfile, User
from app.services.audit import log_event
from app.services.consent import Access, profile_access, resolve_access
from app.services.ingest import normalize as nz
from app.services.ingest.pipeline import post_write_hooks, profile_lock, write_items

router = APIRouter(tags=["review"])

# Field order is the order shown in the review form.
EDITABLE: dict[str, list[str]] = {
    "Condition": ["text", "icd10_guess", "onset_date", "clinical_status"],
    "MedicationRequest": [
        "brand",
        "generic_molecule",
        "strength",
        "form",
        "frequency_text",
        "duration_days",
        "start_date",
        "instructions",
    ],
    "AllergyIntolerance": ["substance", "reaction", "criticality", "recorded_date"],
    "Observation": ["test_name_as_written", "value", "unit_as_written", "reference_range_text", "specimen_date"],
    "Vital": ["name", "value", "unit", "date"],
}


class ReviewItemOut(BaseModel):
    id: uuid.UUID
    document_id: uuid.UUID
    document_label: str
    document_filename: str
    document_mime: str
    document_date: date | None
    source_org_name: str | None
    resource_type: str
    raw: dict[str, Any]
    normalized: dict[str, Any]
    editable: list[str]
    confidence: float
    page: int
    snippet: str | None
    uncertain_reason: str | None
    created_at: datetime


class ReviewAction(BaseModel):
    action: Literal["confirm", "correct", "reject"]
    fields: dict[str, Any] | None = None


@router.get("/profiles/{profile_id}/review", response_model=list[ReviewItemOut])
async def review_queue(
    profile_id: uuid.UUID, access: Access = Depends(profile_access), db: AsyncSession = Depends(get_db)
) -> list[ReviewItemOut]:
    access.require_write()
    rows = (
        await db.execute(
            select(ExtractionItem, Document)
            .join(Document, Document.id == ExtractionItem.document_id)
            .where(Document.profile_id == profile_id, ExtractionItem.review_status == "pending")
            .order_by(Document.seq, ExtractionItem.page)
        )
    ).all()
    return [
        ReviewItemOut(
            id=i.id,
            document_id=d.id,
            document_label=d.label,
            document_filename=d.original_filename,
            document_mime=d.mime,
            document_date=d.document_date,
            source_org_name=d.source_org_name,
            resource_type=i.resource_type,
            raw=i.payload["raw"],
            normalized=i.payload["normalized"],
            editable=EDITABLE.get(i.resource_type, []),
            confidence=i.confidence,
            page=i.page,
            snippet=i.source_snippet,
            uncertain_reason=i.payload["raw"].get("uncertain_reason"),
            created_at=i.created_at,
        )
        for i, d in rows
    ]


@router.post("/review/{item_id}", response_model=dict)
async def review_item(
    item_id: uuid.UUID,
    body: ReviewAction,
    request: Request,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    item = await db.get(ExtractionItem, item_id)
    if item is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Item not found")
    doc = await db.get(Document, item.document_id)
    assert doc is not None
    access = await resolve_access(db, doc.profile_id, user)
    access.require_write()
    if item.review_status != "pending":
        raise HTTPException(status.HTTP_409_CONFLICT, "This item was already reviewed")

    if body.action == "reject":
        item.review_status = "rejected"
    else:
        raw = dict(item.payload["raw"])
        if body.action == "correct":
            if not body.fields:
                raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Nothing to correct")
            unknown = set(body.fields) - set(EDITABLE.get(item.resource_type, []))
            if unknown:
                raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, f"Can't edit: {', '.join(sorted(unknown))}")
            raw.update(body.fields)
        raw["confidence"] = 1.0
        raw["uncertain_reason"] = None
        try:
            normalized = nz.NORMALIZERS[item.resource_type](raw, doc.document_date)
        except (KeyError, TypeError, ValueError) as e:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, f"Invalid value: {e}") from e
        if normalized is None:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "This value couldn't be understood")
        item.payload = {"raw": raw, "normalized": normalized}
        item.confidence = 1.0
        item.review_status = "corrected" if body.action == "correct" else "confirmed"
        profile = await db.get(HealthProfile, doc.profile_id)
        assert profile is not None
        meta = (doc.result_counts or {}).get("meta", {})
        async with profile_lock(profile.id):
            docref = f"DocumentReference/{doc.fhir_document_reference_id}" if doc.fhir_document_reference_id else None
            await write_items(db, profile, doc, [item], meta, existing_docref=docref)
            await db.commit()
            for hook in post_write_hooks:
                await hook(db, profile)

    remaining = await db.scalar(
        select(ExtractionItem.id)
        .where(ExtractionItem.document_id == doc.id, ExtractionItem.review_status == "pending")
        .limit(1)
    )
    if remaining is None and doc.status == "needs_review":
        doc.status = "done"
    counts = dict(doc.result_counts or {})
    counts["pending"] = max(0, int(counts.get("pending", 0)) - 1)
    doc.result_counts = counts
    await log_event(
        db,
        profile_id=doc.profile_id,
        actor_user_id=user.id,
        actor_label=access.actor_label,
        action="upload",
        scopes=["documents"],
        details={"review": body.action, "document": doc.label, "item": item.resource_type},
        ip=client_ip(request),
    )
    await db.commit()
    return {"status": item.review_status, "fhir_resource_id": item.fhir_resource_id, "document_status": doc.status}
