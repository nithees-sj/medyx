"""Admin console: doctor verification (automated evidence + human decisions). No clinical data, ever."""

import re
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db import get_db
from app.deps import require_admin
from app.models import Alert, DoctorDocument, DoctorProfile, Document, HealthProfile, TrustedDomain, User
from app.routers.verification import latest_checks
from app.services import telemetry
from app.services.verification import registry, service

router = APIRouter(prefix="/admin", tags=["admin"])


class CheckRow(BaseModel):
    kind: str
    status: str
    summary: str
    provider: str | None
    details: dict[str, Any]


class DoctorRow(BaseModel):
    user_id: uuid.UUID
    email: str
    full_name: str
    specialty: str
    organization: str
    council: str
    registration_number: str
    verification_status: str
    verification_method: str | None
    review_note: str | None
    created_at: datetime
    verified_at: datetime | None
    last_checked_at: datetime | None
    next_check_at: datetime | None
    decision: str | None
    risk: str | None
    reasons: list[str]
    checks: list[CheckRow]
    certificate: dict[str, Any] | None


class VerifyIn(BaseModel):
    decision: Literal["approve", "reject"]
    note: str | None = Field(default=None, max_length=1000)


class NoteIn(BaseModel):
    note: str | None = Field(default=None, max_length=1000)


async def doctor_row(db: AsyncSession, dp: DoctorProfile, email: str) -> DoctorRow:
    summary = dp.verification_summary or {}
    doc = await db.scalar(
        select(DoctorDocument)
        .where(DoctorDocument.doctor_user_id == dp.user_id)
        .order_by(DoctorDocument.created_at.desc())
    )
    return DoctorRow(
        user_id=dp.user_id,
        email=email,
        full_name=dp.full_name,
        specialty=dp.specialty,
        organization=dp.organization,
        council=dp.council,
        registration_number=dp.registration_number,
        verification_status=dp.verification_status,
        verification_method=dp.verification_method,
        review_note=dp.review_note,
        created_at=dp.created_at,
        verified_at=dp.verified_at,
        last_checked_at=dp.last_checked_at,
        next_check_at=dp.next_check_at,
        decision=summary.get("decision"),
        risk=summary.get("risk"),
        reasons=[r for r in summary.get("reasons", []) if r],
        checks=[
            CheckRow(kind=ch.kind, status=ch.status, summary=ch.summary, provider=ch.provider, details=ch.details)
            for ch in await latest_checks(db, dp.user_id, summary.get("run_id"))
        ],
        certificate={
            "filename": doc.original_filename,
            "mime": doc.mime,
            "uploaded_at": doc.created_at,
            "reading": doc.extracted is None,
        }
        if doc
        else None,
    )


_RISK_ORDER = {"high": 0, "medium": 1, "low": 2, None: 3}


@router.get("/doctors", response_model=list[DoctorRow])
async def list_doctors(
    status_filter: Literal["pending", "verified", "rejected", "suspended", "all"] = "pending",
    _: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> list[DoctorRow]:
    q = select(DoctorProfile, User.email).join(User, User.id == DoctorProfile.user_id)
    if status_filter != "all":
        q = q.where(DoctorProfile.verification_status == status_filter)
    rows = [
        await doctor_row(db, dp, email) for dp, email in (await db.execute(q.order_by(DoctorProfile.created_at))).all()
    ]
    if status_filter == "pending":
        rows.sort(key=lambda r: (_RISK_ORDER.get(r.risk, 3), r.created_at))
    return rows


async def _doctor(db: AsyncSession, user_id: uuid.UUID) -> tuple[DoctorProfile, User]:
    dp = await db.get(DoctorProfile, user_id)
    user = await db.get(User, user_id)
    if dp is None or user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Doctor not found")
    return dp, user


@router.post("/doctors/{user_id}/verify", response_model=DoctorRow)
async def verify_doctor(
    user_id: uuid.UUID,
    body: VerifyIn,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> DoctorRow:
    dp, user = await _doctor(db, user_id)
    if body.decision == "reject" and not (body.note or "").strip():
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "A note is required when rejecting")
    if body.decision == "approve":
        await service.approve(db, dp, by=admin, method="admin", note=body.note)
    else:
        await service.reject(db, dp, by=admin, method="admin", note=(body.note or "").strip())
    await db.commit()
    return await doctor_row(db, dp, user.email)


@router.post("/doctors/{user_id}/recheck", response_model=DoctorRow)
async def recheck_doctor(
    user_id: uuid.UUID, _: User = Depends(require_admin), db: AsyncSession = Depends(get_db)
) -> DoctorRow:
    dp, user = await _doctor(db, user_id)
    await service.run(db, user_id, trigger="admin")
    await db.refresh(dp)
    return await doctor_row(db, dp, user.email)


@router.post("/doctors/{user_id}/suspend", response_model=DoctorRow)
async def suspend_doctor(
    user_id: uuid.UUID, body: NoteIn, admin: User = Depends(require_admin), db: AsyncSession = Depends(get_db)
) -> DoctorRow:
    dp, user = await _doctor(db, user_id)
    if not (body.note or "").strip():
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Give a reason; the doctor will see it")
    if dp.verification_status != "verified":
        raise HTTPException(status.HTTP_409_CONFLICT, "Only verified doctors can be suspended")
    await service.suspend(db, dp, by=admin, reason=(body.note or "").strip(), method="admin")
    await db.commit()
    return await doctor_row(db, dp, user.email)


@router.post("/doctors/{user_id}/reinstate", response_model=DoctorRow)
async def reinstate_doctor(
    user_id: uuid.UUID, body: NoteIn, admin: User = Depends(require_admin), db: AsyncSession = Depends(get_db)
) -> DoctorRow:
    dp, user = await _doctor(db, user_id)
    if dp.verification_status != "suspended":
        raise HTTPException(status.HTTP_409_CONFLICT, "This doctor isn't suspended")
    await service.reinstate(db, dp, by=admin, note=body.note)
    await db.commit()
    return await doctor_row(db, dp, user.email)


@router.get("/doctors/{user_id}/certificate")
async def doctor_certificate(
    user_id: uuid.UUID, _: User = Depends(require_admin), db: AsyncSession = Depends(get_db)
) -> FileResponse:
    doc = await db.scalar(
        select(DoctorDocument)
        .where(DoctorDocument.doctor_user_id == user_id)
        .order_by(DoctorDocument.created_at.desc())
    )
    if doc is None or not Path(doc.storage_path).exists():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No certificate uploaded")
    return FileResponse(
        doc.storage_path,
        media_type=doc.mime,
        filename=doc.original_filename,
        content_disposition_type="inline",
        headers={"Cache-Control": "private, no-store"},
    )


@router.get("/verification/config")
async def verification_config(_: User = Depends(require_admin)) -> dict[str, Any]:
    s = get_settings()
    return {
        "registry": registry.describe(),
        "auto_approve": s.verification_auto_approve,
        "auto_reject": s.verification_auto_reject,
        "recheck_days": s.verification_recheck_days,
        "recheck_job": _job("doctor re-check"),
    }


def _job(name: str) -> dict[str, Any] | None:
    j = telemetry.jobs.get(name)
    return (
        None if j is None else {"last_run": j.last_run, "ok": j.last_ok, "result": j.last_result, "error": j.last_error}
    )


# ───────────────────────────── trusted hospital domains ─────────────────────────────

_DOMAIN_RE = re.compile(r"^(?=.{4,253}$)([a-z0-9-]{1,63}\.)+[a-z]{2,63}$")


class DomainIn(BaseModel):
    domain: str
    organization: str = Field(min_length=2, max_length=200)

    @field_validator("domain")
    @classmethod
    def _domain(cls, v: str) -> str:
        v = v.strip().lower().lstrip("@")
        if not _DOMAIN_RE.fullmatch(v):
            raise ValueError("Enter a domain like kaverikidney.in")
        from app.services.verification.matching import PUBLIC_EMAIL_DOMAINS

        if v in PUBLIC_EMAIL_DOMAINS:
            raise ValueError("Public email providers can't be trusted domains")
        return v


@router.get("/trusted-domains")
async def list_domains(_: User = Depends(require_admin), db: AsyncSession = Depends(get_db)) -> list[dict[str, Any]]:
    rows = (await db.scalars(select(TrustedDomain).order_by(TrustedDomain.domain))).all()
    return [{"domain": d.domain, "organization": d.organization, "created_at": d.created_at} for d in rows]


@router.post("/trusted-domains", status_code=201)
async def add_domain(
    body: DomainIn, admin: User = Depends(require_admin), db: AsyncSession = Depends(get_db)
) -> dict[str, Any]:
    if await db.get(TrustedDomain, body.domain):
        raise HTTPException(status.HTTP_409_CONFLICT, "That domain is already trusted")
    db.add(TrustedDomain(domain=body.domain, organization=body.organization, added_by=admin.id))
    await db.commit()
    telemetry.event(
        "trusted_domain_added", f"{admin.name} trusted @{body.domain} ({body.organization})", user_id=admin.id
    )
    return {"domain": body.domain, "organization": body.organization}


@router.delete("/trusted-domains/{domain}", status_code=204)
async def remove_domain(domain: str, admin: User = Depends(require_admin), db: AsyncSession = Depends(get_db)) -> None:
    row = await db.get(TrustedDomain, domain.lower())
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Not a trusted domain")
    await db.delete(row)
    await db.commit()
    telemetry.event("trusted_domain_removed", f"{admin.name} removed @{domain}", severity="warning", user_id=admin.id)


# ───────────────────────────── aggregate stats (spec §13) ─────────────────────────────


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
