"""Admin console: doctor verification and aggregate stats. No clinical data, ever."""

import uuid
from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db, utcnow
from app.deps import require_admin
from app.models import Alert, DoctorProfile, Document, HealthProfile, User
from app.services import fhir_resources
from app.services.fhir_client import get_fhir
from app.services.notifications import notify

router = APIRouter(prefix="/admin", tags=["admin"])


class DoctorRow(BaseModel):
    user_id: uuid.UUID
    email: str
    full_name: str
    specialty: str
    organization: str
    council: str
    registration_number: str
    verification_status: str
    review_note: str | None
    created_at: datetime
    verified_at: datetime | None


class VerifyIn(BaseModel):
    decision: Literal["approve", "reject"]
    note: str | None = Field(default=None, max_length=1000)


@router.get("/doctors", response_model=list[DoctorRow])
async def list_doctors(
    status_filter: Literal["pending", "verified", "rejected", "all"] = "pending",
    _: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> list[DoctorRow]:
    q = select(DoctorProfile, User.email).join(User, User.id == DoctorProfile.user_id)
    if status_filter != "all":
        q = q.where(DoctorProfile.verification_status == status_filter)
    rows = (await db.execute(q.order_by(DoctorProfile.created_at))).all()
    return [
        DoctorRow(
            user_id=dp.user_id,
            email=email,
            full_name=dp.full_name,
            specialty=dp.specialty,
            organization=dp.organization,
            council=dp.council,
            registration_number=dp.registration_number,
            verification_status=dp.verification_status,
            review_note=dp.review_note,
            created_at=dp.created_at,
            verified_at=dp.verified_at,
        )
        for dp, email in rows
    ]


@router.post("/doctors/{user_id}/verify", response_model=DoctorRow)
async def verify_doctor(
    user_id: uuid.UUID,
    body: VerifyIn,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> DoctorRow:
    dp = await db.get(DoctorProfile, user_id)
    if dp is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Doctor not found")
    if body.decision == "reject" and not (body.note or "").strip():
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "A note is required when rejecting")

    dp.review_note = body.note
    dp.verified_by = admin.id
    dp.verified_at = utcnow()
    if body.decision == "approve":
        dp.verification_status = "verified"
        if not dp.fhir_practitioner_id:
            created = await get_fhir().create(
                fhir_resources.practitioner(
                    full_name=dp.full_name,
                    specialty=dp.specialty,
                    council=dp.council,
                    registration_number=dp.registration_number,
                    organization=dp.organization,
                )
            )
            dp.fhir_practitioner_id = created["id"]
        await notify(
            db,
            user_id,
            "doctor_verified",
            "Your account is verified",
            "You can now accept patient shares.",
            "/doctor",
        )
    else:
        dp.verification_status = "rejected"
        await notify(db, user_id, "doctor_rejected", "Verification was not approved", body.note, "/doctor/profile")
    await db.commit()
    user = await db.get(User, user_id)
    assert user is not None
    return DoctorRow(
        user_id=dp.user_id,
        email=user.email,
        full_name=dp.full_name,
        specialty=dp.specialty,
        organization=dp.organization,
        council=dp.council,
        registration_number=dp.registration_number,
        verification_status=dp.verification_status,
        review_note=dp.review_note,
        created_at=dp.created_at,
        verified_at=dp.verified_at,
    )


@router.get("/stats")
async def stats(_: User = Depends(require_admin), db: AsyncSession = Depends(get_db)) -> dict:
    users_by_role = dict(
        (await db.execute(select(func.coalesce(User.role, "not_onboarded"), func.count()).group_by(User.role))).all()
    )
    docs_by_status = dict((await db.execute(select(Document.status, func.count()).group_by(Document.status))).all())
    alerts_by_type = dict((await db.execute(select(Alert.type, func.count()).group_by(Alert.type))).all())
    return {
        "users": sum(users_by_role.values()),
        "users_by_role": users_by_role,
        "profiles": await db.scalar(select(func.count()).select_from(HealthProfile)),
        "documents_processed": docs_by_status.get("done", 0),
        "documents_by_status": docs_by_status,
        "alerts_by_type": alerts_by_type,
        "doctors_pending": await db.scalar(
            select(func.count()).select_from(DoctorProfile).where(DoctorProfile.verification_status == "pending")
        ),
    }
