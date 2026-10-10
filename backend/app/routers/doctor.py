"""Doctor portal endpoints. Every route requires a *verified* doctor."""

import uuid
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db, utcnow
from app.deps import require_verified_doctor
from app.models import Alert, Consent, Document, HealthProfile, User
from app.routers.alerts import visible_to
from app.services.consent import filter_record
from app.services.profiles import age_on
from app.services.record import load_record

router = APIRouter(prefix="/doctor", tags=["doctor"])


class PatientRow(BaseModel):
    profile_id: uuid.UUID
    name: str
    age: int
    sex: str
    blood_group: str
    healththread_id: str
    scopes: list[str]
    can_write: bool
    expires_at: datetime | None
    critical_alerts: int
    warning_alerts: int
    alert_titles: list[str]
    last_activity: datetime | None
    documents: int
    egfr: list[dict[str, Any]]


@router.get("/patients", response_model=list[PatientRow])
async def my_patients(
    doctor: User = Depends(require_verified_doctor), db: AsyncSession = Depends(get_db)
) -> list[PatientRow]:
    rows = (
        await db.execute(
            select(Consent, HealthProfile)
            .join(HealthProfile, HealthProfile.id == Consent.profile_id)
            .where(Consent.doctor_user_id == doctor.id, Consent.status == "active", Consent.expires_at > utcnow())
        )
    ).all()
    latest: dict[uuid.UUID, tuple[Consent, HealthProfile]] = {}
    for c, p in rows:  # one row per patient (the latest consent wins)
        if p.id not in latest or (c.expires_at or utcnow()) > (latest[p.id][0].expires_at or utcnow()):
            latest[p.id] = (c, p)
    out: list[PatientRow] = []
    for c, p in latest.values():
        record = filter_record(await load_record(db, p), frozenset(c.scopes))
        alerts = (await db.scalars(select(Alert).where(Alert.profile_id == p.id, Alert.status == "active"))).all()
        alerts = [a for a in alerts if not (a.details or {}).get("superseded_by") and visible_to(record, a)]
        last_doc = await db.scalar(select(func.max(Document.created_at)).where(Document.profile_id == p.id))
        n_docs = await db.scalar(select(func.count()).select_from(Document).where(Document.profile_id == p.id))
        out.append(
            PatientRow(
                profile_id=p.id,
                name=p.display_name,
                age=age_on(p.dob),
                sex=p.sex,
                blood_group=p.blood_group,
                healththread_id=p.healththread_id,
                scopes=list(c.scopes),
                can_write=c.can_write,
                expires_at=c.expires_at,
                critical_alerts=sum(a.severity == "critical" for a in alerts),
                warning_alerts=sum(a.severity == "warning" for a in alerts),
                alert_titles=[a.title for a in sorted(alerts, key=lambda a: a.severity != "critical")],
                last_activity=last_doc,
                documents=n_docs or 0,
                egfr=[
                    {"date": o.effective.isoformat(), "value": o.value} for o in record.series("33914-3") if o.effective
                ],
            )
        )
    # Most urgent first: critical alerts, then warnings, then most recent uploads.
    out.sort(
        key=lambda r: (-r.critical_alerts, -r.warning_alerts, -(r.last_activity.timestamp() if r.last_activity else 0))
    )
    return out
