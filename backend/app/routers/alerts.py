"""Safety alerts, re-runs, alert review, and the prescribe-time check."""

import uuid
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.deps import client_ip, current_user
from app.models import Alert, User
from app.services.audit import audit_view, log_event
from app.services.consent import get_scoped_record, resolve_access
from app.services.ingest.pipeline import profile_lock
from app.services.record import PatientRecord
from app.services.safety import engine

router = APIRouter(tags=["alerts"])


def visible_to(record: PatientRecord, alert: Alert) -> bool:
    """A doctor sees an alert only if every piece of its evidence is inside their scoped record."""
    refs = {
        x.ref for coll in (record.conditions, record.medications, record.allergies, record.observations) for x in coll
    }
    return all(e["ref"] in refs for e in alert.evidence)


@router.get("/profiles/{profile_id}/alerts")
async def list_alerts(
    profile_id: uuid.UUID,
    request: Request,
    include: Literal["active", "all"] = "active",
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
) -> list[dict[str, Any]]:
    access, record = await get_scoped_record(db, profile_id, user)
    q = select(Alert).where(Alert.profile_id == profile_id)
    if include == "active":
        q = q.where(Alert.status == "active")
    alerts = [a for a in (await db.scalars(q)).all() if not (a.details or {}).get("superseded_by")]
    if not access.is_owner:
        alerts = [a for a in alerts if visible_to(record, a)]
        await audit_view(db, access, "alerts", sorted(access.scopes), client_ip(request))
    alerts = sorted(
        alerts, key=lambda a: (a.status != "active", engine.SEVERITY_ORDER.get(a.severity, 9), a.created_at)
    )
    return [engine.alert_json(a) for a in alerts]


@router.post("/profiles/{profile_id}/alerts/rerun")
async def rerun(profile_id: uuid.UUID, user: User = Depends(current_user), db: AsyncSession = Depends(get_db)) -> dict:
    access = await resolve_access(db, profile_id, user)
    async with profile_lock(profile_id):
        summary = await engine.run_for_profile(db, access.profile)
    return summary.__dict__


class ReviewIn(BaseModel):
    status: Literal["reviewed_intentional", "resolved", "active"]
    note: str | None = Field(default=None, max_length=2000)


@router.post("/alerts/{alert_id}/review")
async def review_alert(
    alert_id: uuid.UUID,
    body: ReviewIn,
    request: Request,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    alert = await db.get(Alert, alert_id)
    if alert is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Alert not found")
    access, record = await get_scoped_record(db, alert.profile_id, user)
    if access.is_owner:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only a doctor can review an alert")
    if not visible_to(record, alert):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "This alert is outside your access")
    if body.status == "reviewed_intentional" and not (body.note or "").strip():
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Add a note explaining why this is intentional")
    alert.status = body.status
    alert.review_note = body.note
    alert.reviewed_by = user.id
    await log_event(
        db,
        profile_id=alert.profile_id,
        actor_user_id=user.id,
        actor_label=access.actor_label,
        action="alert_review",
        scopes=["medications"],
        details={"alert": alert.title, "status": body.status, "note": body.note},
        ip=client_ip(request),
    )
    await db.commit()
    return engine.alert_json(alert)
