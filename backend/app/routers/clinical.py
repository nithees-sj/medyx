"""Doctor write actions: prescriptions (with live safety check + override), clinical notes, drug search."""

import base64
import hashlib
import io
import uuid
from datetime import UTC, date, datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, Field
from reportlab.lib.colors import HexColor
from reportlab.lib.pagesizes import A5
from reportlab.pdfgen.canvas import Canvas
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app import knowledge as kb
from app.db import get_db
from app.deps import client_ip, current_user
from app.models import ClinicalNote, DoctorProfile, User
from app.services import fhir_resources as fr
from app.services.audit import log_event
from app.services.consent import Access, get_scoped_record, resolve_access
from app.services.fhir_client import get_fhir
from app.services.ingest.pipeline import bump_record_version, post_write_hooks, profile_lock
from app.services.record import load_record
from app.services.safety import engine
from app.services.safety.findings import Finding

router = APIRouter(tags=["clinical"])


def _doctor(access: Access) -> None:
    if access.is_owner or not access.user.doctor_profile:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only a doctor can do this")


def redact(findings: list[Finding], visible_refs: set[str], draft_ref: str) -> list[dict[str, Any]]:
    """Show full detail only when every piece of evidence is inside the doctor's consent.

    The check itself runs on the full record (safety first); a conflict with hidden
    information is reported without revealing it.
    """
    out = []
    for f in findings:
        evidence = [e for e in f.evidence if e.ref != draft_ref]
        if all(e.ref in visible_refs for e in evidence):
            out.append(
                {
                    "rule_id": f.rule_id,
                    "type": f.type,
                    "severity": f.severity,
                    "title": f.title,
                    "clinical_text": f.clinical_text,
                    "patient_text": f.patient_text,
                    "evidence": [e.json() for e in evidence],
                    "redacted": False,
                }
            )
        else:
            out.append(
                {
                    "rule_id": f.rule_id,
                    "type": f.type,
                    "severity": f.severity,
                    "title": "Possible conflict with information outside your access",
                    "clinical_text": "A safety rule fired on parts of the record this patient hasn't shared with you. "
                    "Ask the patient before prescribing.",
                    "patient_text": "",
                    "evidence": [],
                    "redacted": True,
                }
            )
    return out


async def run_check(db: AsyncSession, access: Access, body: "PrescriptionIn") -> tuple[Any, list[dict[str, Any]]]:
    _, scoped = await get_scoped_record(db, access.profile.id, access.user)
    full = await load_record(db, access.profile)
    org = access.user.doctor_profile.organization if access.user.doctor_profile else None
    draft = engine.draft_medication(body.drug, body.strength, body.frequency, body.duration_days, org, engine.today())
    visible = {
        x.ref for coll in (scoped.conditions, scoped.medications, scoped.allergies, scoped.observations) for x in coll
    }
    return draft, redact(engine.check_draft(full, draft), visible, draft.ref)


class PrescriptionIn(BaseModel):
    drug: str = Field(min_length=2, max_length=200)
    strength: str | None = Field(default=None, max_length=50)
    frequency: str | None = Field(default=None, max_length=50)
    duration_days: int | None = Field(default=None, ge=1, le=3650)
    instructions: str | None = Field(default=None, max_length=300)
    override_reason: str | None = Field(default=None, max_length=1000)


@router.post("/profiles/{profile_id}/prescriptions/check")
async def check_prescription(
    profile_id: uuid.UUID, body: PrescriptionIn, user: User = Depends(current_user), db: AsyncSession = Depends(get_db)
) -> dict[str, Any]:
    """Alerts that would fire if this were prescribed — called live as the doctor types."""
    access = await resolve_access(db, profile_id, user)
    draft, alerts = await run_check(db, access, body)
    return {
        "draft": {
            "generic": draft.generic,
            "brand": draft.brand,
            "display": draft.display,
            "classes": sorted(draft.classes),
        },
        "alerts": alerts,
    }


@router.post("/profiles/{profile_id}/prescriptions")
async def prescribe(
    profile_id: uuid.UUID,
    body: PrescriptionIn,
    request: Request,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    access = await resolve_access(db, profile_id, user)
    _doctor(access)
    access.require_write()
    access.require_scope("medications")
    dp = user.doctor_profile
    assert dp is not None
    async with profile_lock(profile_id):
        draft, alerts = await run_check(db, access, body)
        critical = [a for a in alerts if a["severity"] == "critical"]
        if critical and not (body.override_reason or "").strip():
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                {"message": "A critical safety alert needs an override reason", "alerts": critical},
            )
        start = engine.today()
        brand = kb.find_brand(body.drug)
        dose_parts = [
            body.drug,
            body.strength,
            body.frequency,
            f"x {body.duration_days} days" if body.duration_days else None,
        ]
        n = {
            "generic": draft.generic,
            "brand": draft.brand,
            "classes": sorted(draft.classes),
            "display": " ".join(x for x in [draft.display, brand["form"] if brand else None] if x),
            "written_text": " ".join(x for x in dose_parts if x),
            "strength": draft.strength,
            "frequency_text": body.frequency,
            "frequency": {
                "morning": 0,
                "afternoon": 0,
                "night": 0,
                "per_day": draft.per_day,
                "as_needed": draft.as_needed,
            },
            "frequency_label": draft.frequency_label,
            "instructions": body.instructions,
            "route": "oral",
            "start_date": start.isoformat(),
            "end_date": draft.end.isoformat() if draft.end else None,
            "status": "active",
        }
        note = None
        if critical:
            titles = "; ".join(a["title"] for a in critical)
            note = f"Prescribed despite safety alert ({titles}). Reason: {body.override_reason}"
        practitioner = (
            fr.ref(f"Practitioner/{dp.fhir_practitioner_id}", dp.full_name)
            if dp.fhir_practitioner_id
            else {"display": dp.full_name}
        )
        org = {"display": dp.organization}
        resource = fr.medication_request(
            n,
            patient_ref=f"Patient/{access.profile.fhir_patient_id}",
            encounter_ref=None,
            requester=practitioner,
            org=org,
            item={"confidence": 1.0},
            note=note,
        )
        fhir = get_fhir()
        created = await fhir.create(resource)
        mr_ref = f"MedicationRequest/{created['id']}"
        await fhir.create(
            fr.provenance(
                target_ref=mr_ref,
                recorded_instant=datetime.now(UTC).replace(microsecond=0).isoformat(),
                agent=practitioner,
                document_ref=None,
                page=None,
                snippet=None,
            )
        )
        await bump_record_version(db, access.profile)
        await log_event(
            db,
            profile_id=profile_id,
            actor_user_id=user.id,
            actor_label=access.actor_label,
            action="prescribe",
            scopes=["medications"],
            details={
                "medicine": draft.display + (f" ({draft.brand})" if draft.brand else ""),
                "override_reason": body.override_reason if critical else None,
                "alerts": [a["title"] for a in alerts],
            },
            ip=client_ip(request),
        )
        await db.commit()
        for hook in post_write_hooks:
            await hook(db, access.profile)
    return {
        "ref": mr_ref,
        "display": n["display"],
        "alerts": alerts,
        "pdf_url": f"/api/profiles/{profile_id}/prescriptions/{created['id']}.pdf",
    }


@router.get("/profiles/{profile_id}/prescriptions/{mr_id}.pdf")
async def prescription_pdf(
    profile_id: uuid.UUID, mr_id: str, user: User = Depends(current_user), db: AsyncSession = Depends(get_db)
) -> Response:
    access, record = await get_scoped_record(db, profile_id, user)
    access.require_scope("medications")
    med = next((m for m in record.medications if m.ref == f"MedicationRequest/{mr_id}"), None)
    if med is None or not med.requester:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Prescription not found")
    res = await get_fhir().read("MedicationRequest", mr_id)
    requester_ref = (res.get("requester") or {}).get("reference", "")
    dp = await db.scalar(
        select(DoctorProfile).where(DoctorProfile.fhir_practitioner_id == requester_ref.split("/")[-1])
    )
    buf = io.BytesIO()
    w, h = A5
    c = Canvas(buf, pagesize=A5)
    teal = HexColor("#0f6e6e")
    c.setFillColor(teal)
    c.setFont("Helvetica-Bold", 14)
    c.drawString(30, h - 45, dp.full_name if dp else (med.requester or "Doctor"))
    c.setFont("Helvetica", 9)
    c.setFillColor(HexColor("#333333"))
    if dp:
        c.drawString(30, h - 60, f"{dp.specialty} · {dp.organization}")
        c.drawString(30, h - 72, f"{dp.council} Reg. No. {dp.registration_number}")
    c.setStrokeColor(teal)
    c.line(30, h - 82, w - 30, h - 82)
    p = access.profile
    age = date.today().year - p.dob.year
    c.drawString(
        30,
        h - 100,
        f"Patient: {p.display_name}   Age/Sex: {age}/{p.sex[0].upper()}   HealthThread ID: {p.healththread_id}",
    )
    c.drawString(30, h - 114, f"Date: {med.start.strftime('%d %b %Y') if med.start else ''}")
    c.setFont("Helvetica-Bold", 22)
    c.setFillColor(teal)
    c.drawString(30, h - 150, "Rx")
    c.setFillColor(HexColor("#111111"))
    c.setFont("Helvetica-Bold", 12)
    c.drawString(60, h - 175, med.display + (f" ({med.brand})" if med.brand else ""))
    c.setFont("Helvetica", 11)
    duration = f" × {(med.end - med.start).days + 1} days" if med.end and med.start else ""
    c.drawString(
        60, h - 193, f"{med.frequency_label}{duration}{(' · ' + med.instructions) if med.instructions else ''}"
    )
    c.setFont("Helvetica-Oblique", 8)
    c.setFillColor(HexColor("#666666"))
    c.drawString(30, 60, "Signature: ______________________")
    c.drawString(30, 40, "Generated with HealthThread · decision-support checks were run before prescribing.")
    c.drawString(30, 28, "Synthetic demo data.")
    c.showPage()
    c.save()
    return Response(
        buf.getvalue(),
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="prescription-{mr_id}.pdf"'},
    )


# ─────────────────────────────── notes ───────────────────────────────


class NoteIn(BaseModel):
    title: str = Field(min_length=2, max_length=300)
    body: str = Field(min_length=2, max_length=20000)


def note_json(n: ClinicalNote, author: str | None) -> dict[str, Any]:
    return {
        "id": str(n.id),
        "title": n.title,
        "body": n.body,
        "author": author,
        "fhir_document_reference_id": n.fhir_document_reference_id,
        "created_at": n.created_at.isoformat(),
    }


@router.get("/profiles/{profile_id}/notes")
async def list_notes(
    profile_id: uuid.UUID, user: User = Depends(current_user), db: AsyncSession = Depends(get_db)
) -> list[dict[str, Any]]:
    access = await resolve_access(db, profile_id, user)
    q = select(ClinicalNote).where(ClinicalNote.profile_id == profile_id).order_by(ClinicalNote.created_at.desc())
    if not access.is_owner and "notes" not in access.scopes:
        q = q.where(ClinicalNote.author_user_id == user.id)  # a doctor always sees their own notes
    notes = (await db.scalars(q)).all()
    out = []
    for n in notes:
        author = await db.get(User, n.author_user_id)
        out.append(note_json(n, author.name if author else None))
    return out


@router.post("/profiles/{profile_id}/notes")
async def create_note(
    profile_id: uuid.UUID,
    body: NoteIn,
    request: Request,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    access = await resolve_access(db, profile_id, user)
    _doctor(access)
    access.require_write()
    dp = user.doctor_profile
    assert dp is not None
    note = ClinicalNote(profile_id=profile_id, author_user_id=user.id, title=body.title, body=body.body)
    db.add(note)
    await db.flush()
    text = f"{body.title}\n\n{body.body}".encode()
    docref = fr.document_reference(
        patient_ref=f"Patient/{access.profile.fhir_patient_id}",
        doc_id=str(note.id),
        doc_type="clinical_note",
        title=body.title,
        content_type="text/plain; charset=utf-8",
        url="",
        size=len(text),
        sha1_b64=base64.b64encode(hashlib.sha1(text).digest()).decode(),
        created_instant=datetime.now(UTC).replace(microsecond=0).isoformat(),
        document_date=date.today().isoformat(),
        author=fr.ref(f"Practitioner/{dp.fhir_practitioner_id}", dp.full_name)
        if dp.fhir_practitioner_id
        else {"display": dp.full_name},
        category="clinical-note",
        data_b64=base64.b64encode(text).decode(),
    )
    created = await get_fhir().create(docref)
    note.fhir_document_reference_id = created["id"]
    await log_event(
        db,
        profile_id=profile_id,
        actor_user_id=user.id,
        actor_label=access.actor_label,
        action="upload",
        scopes=["notes"],
        details={"note": body.title},
        ip=client_ip(request),
    )
    await db.commit()
    return note_json(note, user.name)


# ─────────────────────────────── drug search ───────────────────────────────


@router.get("/drugs")
async def search_drugs(q: str = "", user: User = Depends(current_user)) -> list[dict[str, Any]]:
    needle = kb.norm_text(q)
    items = kb.drug_catalog()
    if needle:
        items = [i for i in items if needle in kb.norm_text(i["label"]) or needle in kb.norm_text(i["generic"])]
        items.sort(key=lambda i: (not kb.norm_text(i["label"]).startswith(needle), i["label"]))
    return items[:20]
