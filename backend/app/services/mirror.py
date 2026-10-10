"""Best-effort mirroring of consents and audit events to HAPI as FHIR Consent / AuditEvent.

The Postgres rows are the source of truth for enforcement; mirroring runs in the
background so a slow FHIR server never blocks a request.
"""

import asyncio
import logging
import uuid
from datetime import UTC

from app.db import SessionLocal
from app.models import AuditEvent, Consent, DoctorProfile, HealthProfile
from app.services import fhir_resources as fr
from app.services.fhir_client import get_fhir

log = logging.getLogger(__name__)
_tasks: set[asyncio.Task] = set()

FHIR_CONSENT_STATUS = {
    "pending_claim": "proposed",
    "requested": "proposed",
    "active": "active",
    "revoked": "inactive",
    "expired": "inactive",
    "denied": "rejected",
}


def _spawn(coro) -> None:
    try:
        task = asyncio.get_running_loop().create_task(coro)
    except RuntimeError:
        return
    _tasks.add(task)
    task.add_done_callback(_tasks.discard)


def mirror_consent(consent_id: uuid.UUID) -> None:
    _spawn(_mirror_consent(consent_id))


def mirror_audit(event_id: uuid.UUID) -> None:
    _spawn(_mirror_audit(event_id))


async def _mirror_consent(consent_id: uuid.UUID) -> None:
    try:
        async with SessionLocal() as db:
            c = await db.get(Consent, consent_id)
            if c is None:
                return
            profile = await db.get(HealthProfile, c.profile_id)
            if profile is None:
                return
            dp = await db.get(DoctorProfile, c.doctor_user_id) if c.doctor_user_id else None
            practitioner = (
                fr.ref(f"Practitioner/{dp.fhir_practitioner_id}", dp.full_name)
                if dp and dp.fhir_practitioner_id
                else None
            )
            resource = fr.consent(
                patient_ref=f"Patient/{profile.fhir_patient_id}",
                status=FHIR_CONSENT_STATUS.get(c.status, "proposed"),
                created_instant=c.created_at.astimezone(UTC).replace(microsecond=0).isoformat(),
                practitioner_ref=practitioner,
                scopes=list(c.scopes),
                can_write=c.can_write,
                start=None if c.status in ("pending_claim", "requested") else c.created_at.date().isoformat(),
                end=c.expires_at.astimezone(UTC).replace(microsecond=0).isoformat() if c.expires_at else None,
                consent_id=str(c.id),
            )
            fhir = get_fhir()
            if c.fhir_consent_id:
                resource["id"] = c.fhir_consent_id
                await fhir.update(resource)
            else:
                created = await fhir.create(resource)
                c.fhir_consent_id = created["id"]
                await db.commit()
    except Exception:
        log.exception("could not mirror consent %s", consent_id)


async def _mirror_audit(event_id: uuid.UUID) -> None:
    try:
        async with SessionLocal() as db:
            ev = await db.get(AuditEvent, event_id)
            if ev is None:
                return
            profile = await db.get(HealthProfile, ev.profile_id) if ev.profile_id else None
            dp = await db.get(DoctorProfile, ev.actor_user_id) if ev.actor_user_id else None
            agent = (
                fr.ref(f"Practitioner/{dp.fhir_practitioner_id}", ev.actor_label)
                if dp and dp.fhir_practitioner_id
                else {"display": ev.actor_label}
            )
            await get_fhir().create(
                fr.audit_event(
                    patient_ref=f"Patient/{profile.fhir_patient_id}" if profile and profile.fhir_patient_id else None,
                    action=ev.action,
                    recorded=ev.created_at.astimezone(UTC).replace(microsecond=0).isoformat(),
                    agent=agent,
                    ip=ev.ip,
                    description=f"{ev.actor_label}: {ev.action} {', '.join(ev.scopes_touched)}".strip(),
                )
            )
    except Exception:
        log.exception("could not mirror audit event %s", event_id)
