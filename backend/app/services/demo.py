"""Demo personas (DEMO_MODE only). Shared by POST /api/auth/demo and scripts/seed_demo.py."""

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import utcnow
from app.models import DoctorProfile, User
from app.services import fhir_resources
from app.services.fhir_client import get_fhir


@dataclass(frozen=True)
class Persona:
    key: str
    sub: str
    email: str
    name: str
    role: str
    label: str
    doctor: dict | None = None
    verified: bool = False


PERSONAS: dict[str, Persona] = {
    p.key: p
    for p in [
        Persona(
            key="priya",
            sub="demo:priya",
            email="priya.rajan@demo.healththread.app",
            name="Priya Rajan",
            role="patient",
            label="Priya (caregiver)",
        ),
        Persona(
            key="meena",
            sub="demo:meena",
            email="meena.raghavan@demo.healththread.app",
            name="Dr. Meena Raghavan",
            role="doctor",
            label="Dr. Meena Raghavan (verified nephrologist)",
            doctor={
                "full_name": "Dr. Meena Raghavan",
                "specialty": "Nephrology",
                "organization": "Kaveri Kidney Care",
                "council": "Tamil Nadu Medical Council",
                "registration_number": "TNMC-58213",
            },
            verified=True,
        ),
        Persona(
            key="arjun",
            sub="demo:arjun",
            email="arjun.mehta@demo.healththread.app",
            name="Dr. Arjun Mehta",
            role="doctor",
            label="Dr. Arjun Mehta (unverified GP)",
            doctor={
                "full_name": "Dr. Arjun Mehta",
                "specialty": "General Medicine",
                "organization": "Mehta Family Practice",
                "council": "Maharashtra Medical Council",
                "registration_number": "MMC-20417",
            },
        ),
        Persona(
            key="admin",
            sub="demo:admin",
            email="admin@demo.healththread.app",
            name="HealthThread Admin",
            role="admin",
            label="Admin",
        ),
    ]
}


async def ensure_persona(db: AsyncSession, key: str) -> User:
    """Create the persona's user (and doctor profile) if missing; idempotent."""
    p = PERSONAS[key]
    user = await db.scalar(select(User).where(User.google_sub == p.sub))
    if user is None:
        user = User(google_sub=p.sub, email=p.email, name=p.name, role=p.role)
        db.add(user)
        await db.flush()
    existing = await db.get(DoctorProfile, user.id) if p.doctor else None
    if p.doctor and existing is None:
        dp = DoctorProfile(user_id=user.id, **p.doctor)
        if p.verified:
            dp.verification_status = "verified"
            dp.verified_at = utcnow()
            dp.review_note = "Demo persona"
            dp.verification_method = "demo"
            practitioner = await get_fhir().create(fhir_resources.practitioner(**p.doctor))
            dp.fhir_practitioner_id = practitioner["id"]
        db.add(dp)
        await db.flush()
    await db.refresh(user)
    return user
