"""The doctor's side of verification: see what was checked, upload a certificate, fix and resubmit."""

import hashlib
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db import get_db
from app.deps import client_ip, require_doctor
from app.models import DoctorDocument, DoctorProfile, User, VerificationCheck
from app.schemas.auth import DoctorOnboardingIn
from app.services import telemetry
from app.services.documents import ALLOWED, MAX_BYTES, validate_upload
from app.services.notifications import notify_admins
from app.services.verification import matching, service

router = APIRouter(prefix="/doctor/verification", tags=["verification"])

# What a doctor may read about their own checks. Other accounts' ids (duplicate check) and raw
# register payloads stay admin-only.
_DOCTOR_SAFE_DETAILS = {"council_name", "domain", "organization", "read", "name_match", "registration_match",
                        "council_match", "registry_status", "concerns"}  # fmt: skip


class CheckOut(BaseModel):
    kind: str
    status: str
    summary: str
    provider: str | None
    details: dict[str, Any]
    created_at: datetime


async def latest_checks(db: AsyncSession, user_id: uuid.UUID, run_id: str | None) -> list[VerificationCheck]:
    if not run_id:
        return []
    return list(
        (
            await db.scalars(
                select(VerificationCheck)
                .where(VerificationCheck.doctor_user_id == user_id, VerificationCheck.run_id == uuid.UUID(run_id))
                .order_by(VerificationCheck.created_at)
            )
        ).all()
    )


def _doctor_view(ch: VerificationCheck) -> CheckOut:
    summary = ch.summary
    if ch.kind == "duplicate" and ch.status == "failed":
        summary = "This registration number is already linked to another account; an admin will review."
    return CheckOut(
        kind=ch.kind,
        status=ch.status,
        summary=summary,
        provider=ch.provider,
        details={k: v for k, v in (ch.details or {}).items() if k in _DOCTOR_SAFE_DETAILS},
        created_at=ch.created_at,
    )


async def _profile(db: AsyncSession, user: User) -> DoctorProfile:
    dp = await db.get(DoctorProfile, user.id)
    if dp is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No doctor profile")
    return dp


@router.get("")
async def my_verification(user: User = Depends(require_doctor), db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    dp = await _profile(db, user)
    summary = dp.verification_summary or {}
    doc = await db.scalar(
        select(DoctorDocument)
        .where(DoctorDocument.doctor_user_id == user.id)
        .order_by(DoctorDocument.created_at.desc())
    )
    return {
        "status": dp.verification_status,
        "method": dp.verification_method,
        "review_note": dp.review_note,
        "checked_at": dp.last_checked_at,
        "in_progress": bool(doc and doc.extracted is None),
        "certificate": {"filename": doc.original_filename, "uploaded_at": doc.created_at} if doc else None,
        "checks": [_doctor_view(ch) for ch in await latest_checks(db, user.id, summary.get("run_id"))],
        "can_update": dp.verification_status in ("pending", "rejected"),
        "councils": [{"id": co.id, "name": co.name} for co in matching.councils()],
    }


@router.post("/certificate", status_code=202)
async def upload_certificate(
    request: Request,
    file: UploadFile = File(...),
    user: User = Depends(require_doctor),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    dp = await _profile(db, user)
    if dp.verification_status not in ("pending", "rejected"):
        raise HTTPException(status.HTTP_409_CONFLICT, "Your verification is already decided")
    data = await file.read(MAX_BYTES + 1)
    name = Path(file.filename or "certificate").name[:200]
    try:
        mime = validate_upload(data, name)
    except ValueError as e:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(e)) from e
    folder = get_settings().storage_dir / "doctor_documents"
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{uuid.uuid4().hex}{ALLOWED[mime]}"
    path.write_bytes(data)
    doc = DoctorDocument(
        doctor_user_id=user.id,
        original_filename=name,
        mime=mime,
        storage_path=str(path),
        sha256=hashlib.sha256(data).hexdigest(),
    )
    db.add(doc)
    if dp.verification_status == "rejected":
        dp.verification_status = "pending"
    await db.commit()
    telemetry.event(
        "doctor_certificate",
        f"{dp.full_name} uploaded a registration certificate",
        user_id=user.id,
        ip=client_ip(request),
    )
    service.schedule_certificate(doc.id)
    return {"ok": True, "document_id": str(doc.id)}


@router.put("/details")
async def resubmit_details(
    body: DoctorOnboardingIn,
    request: Request,
    user: User = Depends(require_doctor),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    dp = await _profile(db, user)
    if dp.verification_status not in ("pending", "rejected"):
        raise HTTPException(status.HTTP_409_CONFLICT, "Contact an admin to change verified details")
    for k, v in body.model_dump().items():
        setattr(dp, k, v)
    user.name = body.full_name
    dp.verification_status = "pending"
    dp.review_note = None
    await notify_admins(
        db,
        "doctor_pending",
        f"{body.full_name} resubmitted their details",
        f"{body.council} · {body.registration_number}",
        "/admin/doctors",
    )
    await db.commit()
    telemetry.event("doctor_resubmitted", f"{body.full_name} resubmitted verification details", user_id=user.id,
                    ip=client_ip(request))  # fmt: skip
    service.schedule(user.id, "resubmitted")
    return {"ok": True}
