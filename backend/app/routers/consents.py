"""Consent Vault: QR shares, doctor access requests, approvals, revocation, access log."""

import uuid
from datetime import timedelta
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db import get_db, utcnow
from app.deps import client_ip, current_user, require_verified_doctor
from app.models import AuditEvent, Consent, DoctorProfile, HealthProfile, User
from app.rate_limit import CLAIM_LIMIT, limiter
from app.security import hash_token, new_secret_token
from app.services.audit import log_event
from app.services.consent import Access, owner_access
from app.services.mirror import mirror_consent
from app.services.notifications import notify
from app.services.profiles import age_on

router = APIRouter(tags=["consents"])

CLAIM_WINDOW = timedelta(minutes=15)
DURATIONS = (24, 168, 720)  # 24 h, 7 days, 30 days
ScopeName = Literal["conditions", "medications", "allergies", "labs", "documents", "notes", "mental_health"]
DEFAULT_REQUEST_SCOPES: tuple[ScopeName, ...] = ("conditions", "medications", "allergies", "labs")


def _scopes_label(scopes: list[str]) -> str:
    names = {"labs": "lab results", "mental_health": "mental health", "notes": "clinical notes"}
    items = [names.get(s, s) for s in scopes]
    return ", ".join(items[:-1]) + (" and " if len(items) > 1 else "") + items[-1] if items else "nothing"


def _duration_label(hours: int) -> str:
    return {24: "24 hours", 168: "7 days", 720: "30 days"}.get(hours, f"{hours} hours")


async def consent_json(db: AsyncSession, c: Consent) -> dict[str, Any]:
    dp = await db.get(DoctorProfile, c.doctor_user_id) if c.doctor_user_id else None
    doctor_email = None
    if c.doctor_user_id:
        u = await db.get(User, c.doctor_user_id)
        doctor_email = u.email if u else None
    return {
        "id": str(c.id),
        "profile_id": str(c.profile_id),
        "status": c.status,
        "scopes": list(c.scopes),
        "can_write": c.can_write,
        "purpose": c.purpose,
        "duration_hours": c.duration_hours,
        "expires_at": c.expires_at.isoformat() if c.expires_at else None,
        "claim_deadline": c.claim_deadline.isoformat() if c.claim_deadline else None,
        "created_at": c.created_at.isoformat(),
        "revoked_at": c.revoked_at.isoformat() if c.revoked_at else None,
        "doctor": {
            "user_id": str(dp.user_id),
            "name": dp.full_name,
            "specialty": dp.specialty,
            "organization": dp.organization,
            "verified": dp.is_verified,
            "email": doctor_email,
        }
        if dp
        else None,
    }


async def expire_stale(db: AsyncSession) -> int:
    """Mark consents past their expiry / claim deadline. Also enforced at request time."""
    now = utcnow()
    rows = (
        await db.scalars(
            select(Consent).where(
                or_(
                    (Consent.status == "active") & (Consent.expires_at <= now),
                    (Consent.status == "pending_claim") & (Consent.claim_deadline <= now),
                )
            )
        )
    ).all()
    for c in rows:
        c.status = "expired"
    if rows:
        await db.commit()
        for c in rows:
            mirror_consent(c.id)
    return len(rows)


async def _replace_previous(db: AsyncSession, c: Consent) -> None:
    """One active consent per (patient, doctor): a new share or approval replaces the old one."""
    previous = (
        await db.scalars(
            select(Consent).where(
                Consent.profile_id == c.profile_id,
                Consent.doctor_user_id == c.doctor_user_id,
                Consent.status == "active",
                Consent.id != c.id,
            )
        )
    ).all()
    for old in previous:
        old.status = "revoked"
        old.revoked_at = utcnow()
        mirror_consent(old.id)


# ─────────────────────────────── patient: QR share ───────────────────────────────


class ShareIn(BaseModel):
    scopes: list[ScopeName] = Field(min_length=1)
    duration_hours: int = 168
    can_write: bool = False
    purpose: str | None = Field(default=None, max_length=300)

    @field_validator("duration_hours")
    @classmethod
    def _duration(cls, v: int) -> int:
        if v not in DURATIONS:
            raise ValueError("Choose 24 hours, 7 days or 30 days")
        return v


@router.post("/profiles/{profile_id}/shares")
async def create_share(
    profile_id: uuid.UUID,
    body: ShareIn,
    request: Request,
    access: Access = Depends(owner_access),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    token = new_secret_token()
    c = Consent(
        profile_id=profile_id,
        granted_by_user_id=access.user.id,
        scopes=sorted(set(body.scopes)),
        can_write=body.can_write,
        purpose=body.purpose,
        status="pending_claim",
        share_token_hash=hash_token(token),
        claim_deadline=utcnow() + CLAIM_WINDOW,
        duration_hours=body.duration_hours,
    )
    db.add(c)
    await db.flush()
    await log_event(
        db,
        profile_id=profile_id,
        actor_user_id=access.user.id,
        actor_label=access.actor_label,
        action="consent_change",
        scopes=list(c.scopes),
        details={"event": "share_created", "duration": _duration_label(c.duration_hours), "can_write": c.can_write},
        ip=client_ip(request),
    )
    await db.commit()
    mirror_consent(c.id)
    return {
        "consent": await consent_json(db, c),
        "token": token,
        "url": f"{get_settings().app_base_url.rstrip('/')}/share/{token}",
    }


async def _share_by_token(db: AsyncSession, token: str) -> Consent:
    c = await db.scalar(select(Consent).where(Consent.share_token_hash == hash_token(token)))
    if c is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "This share link is not valid")
    return c


@router.get("/share/{token}")
@limiter.limit(CLAIM_LIMIT)
async def preview_share(
    token: str, request: Request, user: User = Depends(current_user), db: AsyncSession = Depends(get_db)
) -> dict[str, Any]:
    c = await _share_by_token(db, token)
    profile = await db.get(HealthProfile, c.profile_id)
    owner = await db.get(User, c.granted_by_user_id) if c.granted_by_user_id else None
    assert profile is not None
    now = utcnow()
    problem = None
    if c.status == "pending_claim" and c.claim_deadline and c.claim_deadline <= now:
        problem = "This QR code has expired. Ask the patient to create a new one."
    elif c.status == "active":
        problem = (
            "already_claimed" if c.doctor_user_id == user.id else "This share has already been used by another doctor."
        )
    elif c.status != "pending_claim":
        problem = "This share is no longer valid."
    elif user.role != "doctor":
        problem = "Only doctors can open a shared record. Sign in with your doctor account."
    elif not user.doctor_profile or not user.doctor_profile.is_verified:
        problem = (
            "Your doctor account is awaiting verification. You can open shared records once an admin verifies you."
        )
    return {
        "patient": {"name": profile.display_name, "age": age_on(profile.dob), "sex": profile.sex},
        "shared_by": owner.name if owner else None,
        "scopes": list(c.scopes),
        "can_write": c.can_write,
        "duration_hours": c.duration_hours,
        "claim_deadline": c.claim_deadline.isoformat() if c.claim_deadline else None,
        "status": c.status,
        "profile_id": str(c.profile_id) if c.doctor_user_id == user.id else None,
        "problem": problem,
    }


@router.post("/share/{token}/claim")
@limiter.limit(CLAIM_LIMIT)
async def claim_share(
    token: str,
    request: Request,
    doctor: User = Depends(require_verified_doctor),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    c = await _share_by_token(db, token)
    now = utcnow()
    if c.status == "active" and c.doctor_user_id == doctor.id:
        return {"consent": await consent_json(db, c), "profile_id": str(c.profile_id)}
    if c.status != "pending_claim":
        raise HTTPException(status.HTTP_409_CONFLICT, "This share is no longer valid")
    if c.claim_deadline and c.claim_deadline <= now:
        c.status = "expired"
        await db.commit()
        raise HTTPException(status.HTTP_410_GONE, "This QR code has expired. Ask the patient to create a new one.")
    c.doctor_user_id = doctor.id
    c.status = "active"
    c.expires_at = now + timedelta(hours=c.duration_hours)
    await _replace_previous(db, c)
    profile = await db.get(HealthProfile, c.profile_id)
    assert profile is not None
    dp = doctor.doctor_profile
    assert dp is not None
    await log_event(
        db,
        profile_id=c.profile_id,
        actor_user_id=doctor.id,
        actor_label=f"{dp.full_name} ({dp.specialty})",
        action="consent_change",
        scopes=list(c.scopes),
        details={"event": "share_claimed", "expires_at": c.expires_at.isoformat()},
        ip=client_ip(request),
    )
    if c.granted_by_user_id:
        await notify(
            db,
            c.granted_by_user_id,
            "share_claimed",
            f"{dp.full_name} ({dp.specialty}) can now see {profile.display_name.split()[0]}'s record",
            f"Access to {_scopes_label(list(c.scopes))} for {_duration_label(c.duration_hours)}.",
            f"/app/p/{profile.id}/sharing",
        )
    await db.commit()
    mirror_consent(c.id)
    return {"consent": await consent_json(db, c), "profile_id": str(c.profile_id)}


# ─────────────────────────────── doctor: access requests ───────────────────────────────


class AccessRequestIn(BaseModel):
    identifier: str = Field(min_length=3, max_length=320)
    scopes: list[ScopeName] = Field(default_factory=lambda: list(DEFAULT_REQUEST_SCOPES))
    duration_hours: int = 168
    purpose: str | None = Field(default=None, max_length=300)

    @field_validator("duration_hours")
    @classmethod
    def _duration(cls, v: int) -> int:
        if v not in DURATIONS:
            raise ValueError("Choose 24 hours, 7 days or 30 days")
        return v


NO_MATCH = "No patient matches that HealthThread ID or email. Check it with the patient."


@router.post("/doctor/requests")
async def request_access(
    body: AccessRequestIn,
    request: Request,
    doctor: User = Depends(require_verified_doctor),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    ident = body.identifier.strip()
    # Exact matches only (no fuzzy search), so the endpoint can't be used to enumerate patients.
    if "@" in ident:
        owner = await db.scalar(select(User).where(func.lower(User.email) == ident.lower(), User.role == "patient"))
        profiles = (
            (await db.scalars(select(HealthProfile).where(HealthProfile.owner_user_id == owner.id))).all()
            if owner
            else []
        )
        if len(profiles) > 1:
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                "This account manages several health profiles. Ask for the HealthThread ID of the right one.",
            )
    else:
        profiles = (await db.scalars(select(HealthProfile).where(HealthProfile.healththread_id == ident.upper()))).all()
    if not profiles:
        raise HTTPException(status.HTTP_404_NOT_FOUND, NO_MATCH)
    profile = profiles[0]
    existing = await db.scalar(
        select(Consent).where(
            Consent.profile_id == profile.id,
            Consent.doctor_user_id == doctor.id,
            Consent.status.in_(["requested", "active"]),
            or_(Consent.expires_at.is_(None), Consent.expires_at > utcnow()),
        )
    )
    if existing:
        raise HTTPException(
            status.HTTP_409_CONFLICT, "You already have a pending request or active access for this patient"
        )
    c = Consent(
        profile_id=profile.id,
        doctor_user_id=doctor.id,
        scopes=sorted(set(body.scopes)),
        can_write=False,
        purpose=body.purpose,
        status="requested",
        duration_hours=body.duration_hours,
    )
    db.add(c)
    await db.flush()
    dp = doctor.doctor_profile
    assert dp is not None
    await log_event(
        db,
        profile_id=profile.id,
        actor_user_id=doctor.id,
        actor_label=f"{dp.full_name} ({dp.specialty})",
        action="consent_change",
        scopes=list(c.scopes),
        details={"event": "access_requested", "purpose": body.purpose},
        ip=client_ip(request),
    )
    await notify(
        db,
        profile.owner_user_id,
        "access_request",
        f"{dp.full_name} ({dp.specialty}) asks to see {profile.display_name.split()[0]}'s record",
        f"Requested: {_scopes_label(list(c.scopes))} for {_duration_label(c.duration_hours)}.",
        f"/app/p/{profile.id}/sharing",
    )
    await db.commit()
    mirror_consent(c.id)
    return {"id": str(c.id), "status": c.status, "healththread_id": profile.healththread_id}


@router.get("/doctor/requests")
async def my_requests(
    doctor: User = Depends(require_verified_doctor), db: AsyncSession = Depends(get_db)
) -> list[dict]:
    rows = (
        await db.execute(
            select(Consent, HealthProfile)
            .join(HealthProfile, HealthProfile.id == Consent.profile_id)
            .where(Consent.doctor_user_id == doctor.id, Consent.status.in_(["requested", "denied"]))
            .order_by(Consent.created_at.desc())
        )
    ).all()
    return [
        {
            "id": str(c.id),
            "status": c.status,
            "healththread_id": p.healththread_id,
            "scopes": list(c.scopes),
            "duration_hours": c.duration_hours,
            "purpose": c.purpose,
            "created_at": c.created_at.isoformat(),
        }
        for c, p in rows
    ]


# ─────────────────────────────── patient: manage consents ───────────────────────────────


@router.get("/profiles/{profile_id}/consents")
async def list_consents(
    profile_id: uuid.UUID, access: Access = Depends(owner_access), db: AsyncSession = Depends(get_db)
) -> list[dict[str, Any]]:
    await expire_stale(db)
    rows = (
        await db.scalars(select(Consent).where(Consent.profile_id == profile_id).order_by(Consent.created_at.desc()))
    ).all()
    return [await consent_json(db, c) for c in rows]


async def _owned_consent(db: AsyncSession, consent_id: uuid.UUID, user: User) -> tuple[Consent, HealthProfile]:
    c = await db.get(Consent, consent_id)
    if c is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Consent not found")
    profile = await db.get(HealthProfile, c.profile_id)
    if profile is None or profile.owner_user_id != user.id or user.role != "patient":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only the account owner can change this")
    return c, profile


class ApproveIn(BaseModel):
    scopes: list[ScopeName] | None = None
    duration_hours: int | None = None
    can_write: bool = False


@router.post("/consents/{consent_id}/approve")
async def approve_request(
    consent_id: uuid.UUID,
    body: ApproveIn,
    request: Request,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    c, profile = await _owned_consent(db, consent_id, user)
    if c.status != "requested":
        raise HTTPException(status.HTTP_409_CONFLICT, "This request was already answered")
    scopes: list[str] = sorted(set(body.scopes)) if body.scopes is not None else list(c.scopes)
    if not set(scopes) <= set(c.scopes) or not scopes:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "You can only narrow the requested access")
    duration = body.duration_hours or c.duration_hours
    if duration > c.duration_hours or duration not in DURATIONS:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "You can only shorten the requested duration")
    c.scopes, c.duration_hours, c.can_write = scopes, duration, body.can_write
    c.status = "active"
    c.granted_by_user_id = user.id
    c.expires_at = utcnow() + timedelta(hours=duration)
    await _replace_previous(db, c)
    await log_event(
        db,
        profile_id=profile.id,
        actor_user_id=user.id,
        actor_label=f"{user.name} (account owner)",
        action="consent_change",
        scopes=scopes,
        details={"event": "request_approved", "duration": _duration_label(duration)},
        ip=client_ip(request),
    )
    if c.doctor_user_id:
        await notify(
            db,
            c.doctor_user_id,
            "request_approved",
            f"Access approved: {profile.display_name}",
            f"{_scopes_label(scopes).capitalize()} for {_duration_label(duration)}.",
            f"/doctor/patients/{profile.id}",
        )
    await db.commit()
    mirror_consent(c.id)
    return await consent_json(db, c)


@router.post("/consents/{consent_id}/deny")
async def deny_request(
    consent_id: uuid.UUID, request: Request, user: User = Depends(current_user), db: AsyncSession = Depends(get_db)
) -> dict[str, Any]:
    c, profile = await _owned_consent(db, consent_id, user)
    if c.status != "requested":
        raise HTTPException(status.HTTP_409_CONFLICT, "This request was already answered")
    c.status = "denied"
    await log_event(
        db,
        profile_id=profile.id,
        actor_user_id=user.id,
        actor_label=f"{user.name} (account owner)",
        action="consent_change",
        details={"event": "request_denied"},
        ip=client_ip(request),
    )
    if c.doctor_user_id:
        await notify(
            db,
            c.doctor_user_id,
            "request_denied",
            f"Access request declined ({profile.healththread_id})",
            None,
            "/doctor/requests",
        )
    await db.commit()
    mirror_consent(c.id)
    return await consent_json(db, c)


@router.post("/consents/{consent_id}/revoke")
async def revoke(
    consent_id: uuid.UUID, request: Request, user: User = Depends(current_user), db: AsyncSession = Depends(get_db)
) -> dict[str, Any]:
    c, profile = await _owned_consent(db, consent_id, user)
    if c.status not in ("active", "pending_claim", "requested"):
        raise HTTPException(status.HTTP_409_CONFLICT, "This access has already ended")
    was_active = c.status == "active"
    c.status = "revoked"
    c.revoked_at = utcnow()
    await log_event(
        db,
        profile_id=profile.id,
        actor_user_id=user.id,
        actor_label=f"{user.name} (account owner)",
        action="consent_change",
        scopes=list(c.scopes),
        details={"event": "revoked"},
        ip=client_ip(request),
    )
    if was_active and c.doctor_user_id:
        await notify(
            db,
            c.doctor_user_id,
            "access_revoked",
            f"Access to {profile.display_name}'s record was revoked",
            "The patient ended this share.",
            "/doctor",
        )
    await db.commit()
    mirror_consent(c.id)
    return await consent_json(db, c)


# ─────────────────────────────── access log ───────────────────────────────

ACTION_VERB = {
    "view": "viewed",
    "upload": "added to the record",
    "prescribe": "prescribed",
    "chat": "asked the copilot about",
    "summary": "opened a summary of",
    "export": "exported",
    "emergency_view": "opened the emergency card",
    "consent_change": "changed sharing",
    "alert_review": "reviewed an alert",
}


@router.get("/profiles/{profile_id}/audit")
async def access_log(
    profile_id: uuid.UUID,
    access: Access = Depends(owner_access),
    db: AsyncSession = Depends(get_db),
    limit: int = 200,
) -> list[dict[str, Any]]:
    rows = (
        await db.scalars(
            select(AuditEvent)
            .where(AuditEvent.profile_id == profile_id)
            .order_by(AuditEvent.created_at.desc())
            .limit(min(limit, 500))
        )
    ).all()
    out = []
    for e in rows:
        out.append(
            {
                "id": str(e.id),
                "actor": e.actor_label,
                "actor_is_owner": e.actor_user_id == access.user.id,
                "action": e.action,
                "verb": ACTION_VERB.get(e.action, e.action),
                "scopes": list(e.scopes_touched),
                "details": e.details,
                "ip": e.ip,
                "created_at": e.created_at.isoformat(),
            }
        )
    return out
