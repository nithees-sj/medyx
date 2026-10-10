import uuid

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.deps import require_patient
from app.models import Alert, Document, ExtractionItem, HealthProfile, User
from app.schemas.auth import ProfileIn
from app.schemas.profile import ProfileOut, ProfileSummaryOut
from app.services import fhir_resources
from app.services.consent import Access, owner_access, profile_access
from app.services.fhir_client import get_fhir
from app.services.profiles import create_profile

router = APIRouter(prefix="/profiles", tags=["profiles"])


async def _summaries(db: AsyncSession, profiles: list[HealthProfile]) -> list[ProfileSummaryOut]:
    ids = [p.id for p in profiles]
    if not ids:
        return []
    alert_rows = (
        await db.execute(
            select(Alert.profile_id, Alert.severity, func.count())
            .where(Alert.profile_id.in_(ids), Alert.status == "active")
            .group_by(Alert.profile_id, Alert.severity)
        )
    ).all()
    doc_rows = (
        await db.execute(
            select(Document.profile_id, func.count())
            .where(Document.profile_id.in_(ids))
            .group_by(Document.profile_id)
        )
    ).all()
    pending_rows = (
        await db.execute(
            select(Document.profile_id, func.count())
            .join(ExtractionItem, ExtractionItem.document_id == Document.id)
            .where(Document.profile_id.in_(ids), ExtractionItem.review_status == "pending")
            .group_by(Document.profile_id)
        )
    ).all()
    out = []
    for p in profiles:
        s = ProfileSummaryOut.model_validate(p, from_attributes=True)
        s.active_alerts = sum(n for pid, _, n in alert_rows if pid == p.id)
        s.critical_alerts = sum(n for pid, sev, n in alert_rows if pid == p.id and sev == "critical")
        s.documents = next((n for pid, n in doc_rows if pid == p.id), 0)
        s.pending_review = next((n for pid, n in pending_rows if pid == p.id), 0)
        out.append(s)
    return out


@router.get("", response_model=list[ProfileSummaryOut])
async def list_profiles(
    user: User = Depends(require_patient), db: AsyncSession = Depends(get_db)
) -> list[ProfileSummaryOut]:
    profiles = (
        await db.scalars(
            select(HealthProfile)
            .where(HealthProfile.owner_user_id == user.id)
            .order_by(HealthProfile.relationship != "self", HealthProfile.created_at)
        )
    ).all()
    return await _summaries(db, list(profiles))


@router.post("", response_model=ProfileOut, status_code=201)
async def add_profile(
    body: ProfileIn, user: User = Depends(require_patient), db: AsyncSession = Depends(get_db)
) -> HealthProfile:
    profile = await create_profile(db, owner_user_id=user.id, **body.model_dump())
    await db.commit()
    return profile


@router.get("/{profile_id}", response_model=ProfileSummaryOut)
async def get_profile(
    profile_id: uuid.UUID, access: Access = Depends(profile_access), db: AsyncSession = Depends(get_db)
) -> ProfileSummaryOut:
    # Demographics are always part of any consent.
    return (await _summaries(db, [access.profile]))[0]


@router.patch("/{profile_id}", response_model=ProfileOut)
async def update_profile(
    profile_id: uuid.UUID,
    body: ProfileIn,
    access: Access = Depends(owner_access),
    db: AsyncSession = Depends(get_db),
) -> HealthProfile:
    p = access.profile
    for k, v in body.model_dump().items():
        setattr(p, k, v)
    resource = fhir_resources.patient(
        name=p.display_name,
        dob=p.dob,
        sex=p.sex,
        blood_group=p.blood_group,
        healththread_id=p.healththread_id,
        emergency_contact_name=p.emergency_contact_name,
        emergency_contact_phone=p.emergency_contact_phone,
    )
    resource["id"] = p.fhir_patient_id
    await get_fhir().update(resource)
    await db.commit()
    return p
