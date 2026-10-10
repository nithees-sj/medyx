"""Read views of the merged record, and the FHIR Bundle export."""

import asyncio
import contextlib
import uuid
from typing import Any

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db import get_db
from app.deps import client_ip
from app.services.audit import log_event
from app.services.consent import Access, owner_access
from app.services.fhir_client import get_fhir
from app.services.fhir_resources import validate

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
