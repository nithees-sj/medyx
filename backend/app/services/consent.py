"""Consent enforcement.

`resolve_access()` decides whether a viewer may open a health profile at all, and with
which scopes. `get_scoped_record()` (added with the record engine) is the only way
doctor-facing code reads clinical data, and filters every resource by those scopes.
"""

import uuid
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from fastapi import Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db, utcnow
from app.deps import current_user
from app.models import Consent, HealthProfile, User
from app.models.clinical import SCOPES

if TYPE_CHECKING:
    from app.services.record import PatientRecord

ALL_SCOPES: frozenset[str] = frozenset(SCOPES)
DEFAULT_SHARE_SCOPES = ("conditions", "medications", "allergies", "labs")


@dataclass
class Access:
    profile: HealthProfile
    user: User
    is_owner: bool
    scopes: frozenset[str]
    can_write: bool
    consent: Consent | None = None
    extra: dict = field(default_factory=dict)

    @property
    def is_doctor(self) -> bool:
        return not self.is_owner

    @property
    def actor_label(self) -> str:
        if self.is_owner:
            return f"{self.user.name} (account owner)"
        dp = self.user.doctor_profile
        return f"{dp.full_name} ({dp.specialty})" if dp else self.user.name

    def require_scope(self, scope: str) -> None:
        if scope not in self.scopes:
            raise HTTPException(status.HTTP_403_FORBIDDEN, f"Your access does not include {scope}")

    def require_write(self) -> None:
        if not self.can_write:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Your access is read-only")


async def active_consent(db: AsyncSession, profile_id: uuid.UUID, doctor_id: uuid.UUID) -> Consent | None:
    """The doctor's active, unexpired consent for this profile, expiring stale rows on the way."""
    rows = (
        await db.scalars(
            select(Consent).where(
                Consent.profile_id == profile_id,
                Consent.doctor_user_id == doctor_id,
                Consent.status == "active",
            )
        )
    ).all()
    now = utcnow()
    best: Consent | None = None
    for c in rows:
        if c.expires_at is not None and c.expires_at <= now:
            c.status = "expired"
            continue
        if best is None or (c.expires_at or now) > (best.expires_at or now):
            best = c
    if any(c.status == "expired" for c in rows):
        await db.commit()
    return best


async def resolve_access(db: AsyncSession, profile_id: uuid.UUID, user: User) -> Access:
    profile = await db.get(HealthProfile, profile_id)
    if profile is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Profile not found")

    if user.role == "patient" and profile.owner_user_id == user.id:
        return Access(profile=profile, user=user, is_owner=True, scopes=ALL_SCOPES, can_write=True)

    if user.role == "doctor":
        if not user.doctor_profile or not user.doctor_profile.is_verified:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Doctor account is awaiting verification")
        consent = await active_consent(db, profile_id, user.id)
        if consent is None:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "No active consent for this patient")
        return Access(
            profile=profile,
            user=user,
            is_owner=False,
            scopes=frozenset(consent.scopes),
            can_write=consent.can_write,
            consent=consent,
        )

    # Admins and other patients never see clinical data.
    raise HTTPException(status.HTTP_403_FORBIDDEN, "You do not have access to this profile")


async def profile_access(
    profile_id: uuid.UUID, user: User = Depends(current_user), db: AsyncSession = Depends(get_db)
) -> Access:
    return await resolve_access(db, profile_id, user)


async def owner_access(access: Access = Depends(profile_access)) -> Access:
    if not access.is_owner:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only the account owner can do this")
    return access


# ─────────────────────────────── Scoped record (the only doctor read path) ───────────────────────────────


def filter_record(record: "PatientRecord", scopes: frozenset[str]) -> "PatientRecord":
    """Return a copy of the record containing only what `scopes` allow.

    Demographics are always included. Mental-health conditions/medicines need the
    `mental_health` scope on top of `conditions`/`medications`.
    """
    from app.services.record import PatientRecord

    mh = "mental_health" in scopes
    conditions = [c for c in record.conditions if "conditions" in scopes and (mh or not c.mental_health)]
    medications = [m for m in record.medications if "medications" in scopes and (mh or not m.psychiatric)]
    allergies = list(record.allergies) if "allergies" in scopes else []
    observations = list(record.observations) if "labs" in scopes else []

    # A document opens through a citation only if *everything* extracted from it is visible to this
    # viewer, so an out-of-scope item on the same page (a prescription next to a temperature, or a
    # mental-health diagnosis) can never leak through the source viewer.
    visible = {x.ref for coll in (conditions, medications, allergies, observations) for x in coll}
    items_by_doc: dict[str, set[str]] = {}
    for coll in (record.conditions, record.medications, record.allergies, record.observations):
        for x in coll:
            for s in x.sources:
                items_by_doc.setdefault(s.document_id, set()).add(x.ref)
    documents = []
    for d in record.documents:
        granted = (d.category == "uploaded" and "documents" in scopes) or (
            d.category == "clinical_note" and "notes" in scopes
        )
        items = items_by_doc.get(d.id, set())
        fully_visible = bool(items) and items <= visible
        hides_mental_health = any(
            (getattr(x, "mental_health", False) or getattr(x, "psychiatric", False))
            and x.ref in items
            and x.ref not in visible
            for coll in (record.conditions, record.medications)
            for x in coll
        )
        if (granted and not hides_mental_health) or fully_visible:
            documents.append(d)
    scoped = PatientRecord(
        profile_id=record.profile_id,
        version=record.version,
        patient_ref=record.patient_ref,
        display_name=record.display_name,
        dob=record.dob,
        sex=record.sex,
        blood_group=record.blood_group,
        conditions=conditions,
        medications=medications,
        allergies=allergies,
        observations=observations,
        documents=documents,
    )
    scoped.listable_document_ids = {
        d.id
        for d in documents
        if (d.category == "uploaded" and "documents" in scopes) or (d.category == "clinical_note" and "notes" in scopes)
    }
    return scoped


async def get_scoped_record(db: AsyncSession, profile_id: uuid.UUID, viewer: User) -> tuple[Access, "PatientRecord"]:
    """Check consent (active, unexpired, verified doctor) and return the record filtered by scope.

    Every doctor-facing endpoint (workspace, timeline, trends, documents, summary, chat,
    insights, prescriptions) reads clinical data through this function.
    """
    from app.services.record import load_record

    access = await resolve_access(db, profile_id, viewer)
    record = await load_record(db, access.profile)
    if access.is_owner:
        record.listable_document_ids = {d.id for d in record.documents}
        return access, record
    return access, filter_record(record, access.scopes)


async def scoped_record_for(db: AsyncSession, access: Access) -> "PatientRecord":
    _, record = await get_scoped_record(db, access.profile.id, access.user)
    return record
