"""Health profile creation (app row + FHIR Patient + HealthThread ID)."""

import secrets
import uuid
from datetime import date

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import HealthProfile
from app.services import fhir_resources
from app.services.fhir_client import get_fhir

# No 0/O, 1/I/L: easy to read aloud and type from a card.
_ALPHABET = "23456789ABCDEFGHJKMNPQRSTUVWXYZ"


def generate_healththread_id() -> str:
    chars = "".join(secrets.choice(_ALPHABET) for _ in range(8))
    return f"HT-{chars[:4]}-{chars[4:]}"


async def _unique_healththread_id(db: AsyncSession) -> str:
    while True:
        candidate = generate_healththread_id()
        exists = await db.scalar(select(HealthProfile.id).where(HealthProfile.healththread_id == candidate))
        if not exists:
            return candidate


async def create_profile(
    db: AsyncSession,
    *,
    owner_user_id: uuid.UUID,
    display_name: str,
    relationship: str,
    dob: date,
    sex: str,
    blood_group: str,
    emergency_contact_name: str | None,
    emergency_contact_phone: str | None,
) -> HealthProfile:
    ht_id = await _unique_healththread_id(db)
    patient = fhir_resources.patient(
        name=display_name,
        dob=dob,
        sex=sex,
        blood_group=blood_group,
        healththread_id=ht_id,
        emergency_contact_name=emergency_contact_name,
        emergency_contact_phone=emergency_contact_phone,
    )
    created = await get_fhir().create(patient)
    profile = HealthProfile(
        owner_user_id=owner_user_id,
        display_name=display_name,
        relationship=relationship,
        fhir_patient_id=created["id"],
        dob=dob,
        sex=sex,
        blood_group=blood_group,
        emergency_contact_name=emergency_contact_name,
        emergency_contact_phone=emergency_contact_phone,
        healththread_id=ht_id,
    )
    db.add(profile)
    await db.flush()
    return profile


def age_on(dob: date, today: date | None = None) -> int:
    today = today or date.today()
    return today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))
