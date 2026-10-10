"""Read views of the merged record, and the FHIR Bundle export."""

import asyncio
import contextlib
import uuid
from datetime import date
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db import get_db
from app.deps import client_ip, current_user
from app.models import User
from app.services import views
from app.services.audit import audit_view, log_event
from app.services.consent import Access, get_scoped_record, owner_access
from app.services.fhir_client import get_fhir
from app.services.fhir_resources import validate
from app.services.ingest.pipeline import bump_record_version, profile_lock

router = APIRouter(tags=["record"])

PATIENT_TYPES = {
    "Condition": "subject",
    "Observation": "subject",
    "MedicationRequest": "subject",
    "AllergyIntolerance": "patient",
    "Encounter": "subject",
    "DiagnosticReport": "subject",
    "DocumentReference": "subject",
    "Consent": "patient",
    "AuditEvent": "patient",
}


def _references(node: Any, out: set[str]) -> None:
    if isinstance(node, dict):
        for k, v in node.items():
            if k == "reference" and isinstance(v, str) and v.count("/") == 1:
                out.add(v)
            else:
                _references(v, out)
    elif isinstance(node, list):
        for v in node:
            _references(v, out)


async def export_bundle(patient_id: str) -> dict[str, Any]:
    fhir = get_fhir()
    patient_ref = f"Patient/{patient_id}"
    results = await asyncio.gather(
        *(fhir.search(t, {p: patient_ref}) for t, p in PATIENT_TYPES.items()), return_exceptions=True
    )
    resources: dict[str, dict[str, Any]] = {patient_ref: await fhir.read("Patient", patient_id)}
    for found in results:
        if isinstance(found, BaseException):
            continue
        for r in found:
            resources[f"{r['resourceType']}/{r['id']}"] = r

    # Provenance for every clinical resource, found through the documents they cite.
    doc_refs = [k for k in resources if k.startswith("DocumentReference/")]
    prov_lists = await asyncio.gather(*(fhir.search("Provenance", {"entity": d}) for d in doc_refs))
    for found in prov_lists:
        for r in found:
            resources[f"Provenance/{r['id']}"] = r
    # Doctor-authored resources carry Provenance without a document entity.
    for target in [k for k in resources if k.startswith(("MedicationRequest/", "DocumentReference/"))]:
        for r in await fhir.search("Provenance", {"target": target}):
            resources[f"Provenance/{r['id']}"] = r

    # Referenced Organizations and Practitioners.
    refs: set[str] = set()
    _references(list(resources.values()), refs)
    for ref in sorted(refs):
        rtype, rid = ref.split("/")
        if rtype in ("Organization", "Practitioner") and ref not in resources:
            with contextlib.suppress(Exception):
                resources[ref] = await fhir.read(rtype, rid)

    base = get_settings().fhir_base_url.rstrip("/")
    bundle = {
        "resourceType": "Bundle",
        "type": "collection",
        "meta": {"tag": [{"system": "https://healththread.app/fhir/tag", "code": "patient-export"}]},
        "entry": [{"fullUrl": f"{base}/{k}", "resource": v} for k, v in resources.items()],
    }
    return bundle


@router.get("/profiles/{profile_id}/export")
async def export_record(
    profile_id: uuid.UUID, request: Request, access: Access = Depends(owner_access), db: AsyncSession = Depends(get_db)
) -> dict[str, Any]:
    bundle = await export_bundle(access.profile.fhir_patient_id or "")
    validate(bundle)
    await log_event(
        db,
        profile_id=profile_id,
        actor_user_id=access.user.id,
        actor_label=access.actor_label,
        action="export",
        details={"resources": len(bundle["entry"])},
        ip=client_ip(request),
    )
    await db.commit()
    return bundle


def _today() -> date:
    return date.today()


@router.get("/profiles/{profile_id}/orgs")
async def organizations(
    profile_id: uuid.UUID, user: User = Depends(current_user), db: AsyncSession = Depends(get_db)
) -> dict[str, str]:
    _, record = await get_scoped_record(db, profile_id, user)
    return views.org_colors(record)


@router.get("/profiles/{profile_id}/timeline")
async def timeline(
    profile_id: uuid.UUID, request: Request, user: User = Depends(current_user), db: AsyncSession = Depends(get_db)
) -> dict[str, Any]:
    access, record = await get_scoped_record(db, profile_id, user)
    await audit_view(db, access, "timeline", sorted(access.scopes), client_ip(request))
    return views.timeline(record, _today())


@router.get("/profiles/{profile_id}/trends")
async def trends(
    profile_id: uuid.UUID, request: Request, user: User = Depends(current_user), db: AsyncSession = Depends(get_db)
) -> dict[str, Any]:
    access, record = await get_scoped_record(db, profile_id, user)
    await audit_view(db, access, "trends", ["labs"], client_ip(request))
    return {"analytes": views.trends(record), "org_colors": views.org_colors(record)}


@router.get("/profiles/{profile_id}/medications")
async def medications(
    profile_id: uuid.UUID, request: Request, user: User = Depends(current_user), db: AsyncSession = Depends(get_db)
) -> dict[str, Any]:
    access, record = await get_scoped_record(db, profile_id, user)
    await audit_view(db, access, "medications", ["medications"], client_ip(request))
    today = _today()
    meds = [views.medication_json(m, today) for m in record.medications]
    meds.sort(key=lambda m: (m["status"] != "active", m["start"] or ""), reverse=False)
    return {"medications": meds, "org_colors": views.org_colors(record)}


class StopMedicationIn(BaseModel):
    ref: str


@router.post("/profiles/{profile_id}/medications/stop")
async def stop_medication(
    profile_id: uuid.UUID,
    body: StopMedicationIn,
    request: Request,
    access: Access = Depends(owner_access),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """The patient/caregiver records that a medicine is no longer being taken."""
    rtype, _, rid = body.ref.partition("/")
    if rtype != "MedicationRequest" or not rid:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Not a medication reference")
    fhir = get_fhir()
    async with profile_lock(access.profile.id):
        res = await fhir.read("MedicationRequest", rid)
        if (res.get("subject") or {}).get("reference") != f"Patient/{access.profile.fhir_patient_id}":
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Medication not found")
        today = _today().isoformat()
        res["status"] = "stopped"
        for d in res.get("dosageInstruction", []):
            bounds = d.setdefault("timing", {}).setdefault("repeat", {}).setdefault("boundsPeriod", {})
            bounds["end"] = today
        res.setdefault("note", []).append({"text": f"Marked as stopped by {access.user.name} on {today}"})
        await fhir.update(res)
        await bump_record_version(db, access.profile)
        await log_event(
            db,
            profile_id=access.profile.id,
            actor_user_id=access.user.id,
            actor_label=access.actor_label,
            action="upload",
            scopes=["medications"],
            details={"medication_stopped": body.ref},
            ip=client_ip(request),
        )
        await db.commit()
        from app.services.ingest.pipeline import post_write_hooks

        for hook in post_write_hooks:
            await hook(db, access.profile)
    return {"ok": True, "ref": body.ref, "status": "stopped"}
