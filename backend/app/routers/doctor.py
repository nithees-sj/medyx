"""Doctor portal endpoints. Every route requires a *verified* doctor."""

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db, utcnow
from app.deps import require_verified_doctor
from app.models import Consent, HealthProfile, User
from app.services.profiles import age_on

router = APIRouter(prefix="/doctor", tags=["doctor"])


class PatientRow(BaseModel):
    profile_id: uuid.UUID
    name: str
    age: int
    sex: str
    healththread_id: str
    scopes: list[str]
    can_write: bool
    expires_at: datetime | None


@router.get("/patients", response_model=list[PatientRow])
async def my_patients(
    doctor: User = Depends(require_verified_doctor), db: AsyncSession = Depends(get_db)
) -> list[PatientRow]:
    rows = (
        await db.execute(
            select(Consent, HealthProfile)
            .join(HealthProfile, HealthProfile.id == Consent.profile_id)
            .where(
                Consent.doctor_user_id == doctor.id,
                Consent.status == "active",
                Consent.expires_at > utcnow(),
            )
        )
    ).all()
    return [
        PatientRow(
            profile_id=p.id,
            name=p.display_name,
            age=age_on(p.dob),
            sex=p.sex,
            healththread_id=p.healththread_id,
            scopes=c.scopes,
            can_write=c.can_write,
            expires_at=c.expires_at,
        )
        for c, p in rows
    ]
