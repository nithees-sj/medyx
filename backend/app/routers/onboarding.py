from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.deps import current_user
from app.models import DoctorProfile, User
from app.routers.auth import start_session
from app.schemas.auth import DoctorOnboardingIn, LoginOut, PatientOnboardingIn
from app.services.notifications import notify_admins
from app.services.profiles import create_profile

router = APIRouter(prefix="/onboarding", tags=["onboarding"])


def _ensure_not_onboarded(user: User) -> None:
    if user.role is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Account is already set up")


@router.post("/patient", response_model=LoginOut)
async def onboard_patient(
    body: PatientOnboardingIn,
    response: Response,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
) -> LoginOut:
    _ensure_not_onboarded(user)
    user.name = body.name
    user.role = "patient"
    await create_profile(db, owner_user_id=user.id, **body.profile.model_dump())
    await db.commit()
    await db.refresh(user)
    return start_session(response, user)


@router.post("/doctor", response_model=LoginOut)
async def onboard_doctor(
    body: DoctorOnboardingIn,
    response: Response,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
) -> LoginOut:
    _ensure_not_onboarded(user)
    user.name = body.full_name
    user.role = "doctor"
    db.add(DoctorProfile(user_id=user.id, **body.model_dump()))
    await notify_admins(
        db,
        "doctor_pending",
        f"{body.full_name} ({body.specialty}) is awaiting verification",
        f"{body.council} · {body.registration_number}",
        "/admin",
    )
    await db.commit()
    await db.refresh(user, ["doctor_profile"])
    return start_session(response, user)
