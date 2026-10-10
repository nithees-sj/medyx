"""Consent enforcement.

`resolve_access()` decides whether a viewer may open a health profile at all, and with
which scopes. `get_scoped_record()` (added with the record engine) is the only way
doctor-facing code reads clinical data, and filters every resource by those scopes.
"""

import uuid
from dataclasses import dataclass, field

from fastapi import Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db, utcnow
from app.deps import current_user
from app.models import Consent, HealthProfile, User
from app.models.clinical import SCOPES

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
