"""Remove a profile's clinical data from HAPI and Postgres (seed --reset, profile deletion)."""

import asyncio
import contextlib
import logging
from pathlib import Path

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Alert, AuditEvent, ChatMessage, ClinicalNote, Consent, Document, HealthProfile, SummaryCache
from app.services import record as record_service
from app.services.fhir_client import FhirError, get_fhir

log = logging.getLogger(__name__)

# Delete in dependency order: things that reference others first.
DELETE_ORDER = [
    ("Provenance", None),
    ("AuditEvent", "patient"),
    ("Consent", "patient"),
    ("DiagnosticReport", "subject"),
    ("Observation", "subject"),
    ("MedicationRequest", "subject"),
    ("Condition", "subject"),
    ("AllergyIntolerance", "patient"),
    ("Encounter", "subject"),
    ("DocumentReference", "subject"),
]


async def purge_fhir(patient_id: str, delete_patient: bool = False) -> int:
    fhir = get_fhir()
    patient_ref = f"Patient/{patient_id}"
    removed = 0
    docrefs = await fhir.search("DocumentReference", {"subject": patient_ref})
    targets: list[str] = []
    for rtype, param in DELETE_ORDER:
        if rtype == "Provenance":
            found = []
            for d in docrefs:
                found += await fhir.search("Provenance", {"entity": f"DocumentReference/{d['id']}"})
            for t in ("MedicationRequest", "DocumentReference"):
                for r in await fhir.search(t, {"subject": patient_ref}):
                    targets.append(f"{t}/{r['id']}")
            for t in targets:
                found += await fhir.search("Provenance", {"target": t})
        else:
            found = await fhir.search(rtype, {param or "subject": patient_ref})
        seen = set()
        for r in found:
            if r["id"] in seen:
                continue
            seen.add(r["id"])
            try:
                await fhir.delete(r["resourceType"], r["id"])
                removed += 1
            except FhirError as e:
                log.warning("could not delete %s/%s: %s", r["resourceType"], r["id"], e)
        await asyncio.sleep(0)
    if delete_patient:
        try:
            await fhir.delete("Patient", patient_id)
        except FhirError as e:
            log.warning("could not delete Patient/%s: %s", patient_id, e)
    return removed


async def purge_profile(db: AsyncSession, profile: HealthProfile, delete_profile: bool = False) -> None:
    if profile.fhir_patient_id:
        await purge_fhir(profile.fhir_patient_id, delete_patient=delete_profile)
    for model in (Alert, AuditEvent, ChatMessage, ClinicalNote, Consent, SummaryCache):
        await db.execute(delete(model).where(model.profile_id == profile.id))
    docs = (await db.scalars(select(Document).where(Document.profile_id == profile.id))).all()
    for d in docs:
        with contextlib.suppress(OSError):
            Path(d.storage_path).unlink(missing_ok=True)
        await db.delete(d)
    if delete_profile:
        await db.delete(profile)
    else:
        profile.record_version += 1
    record_service.invalidate(profile.id)
    await db.commit()
