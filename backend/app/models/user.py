import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base, utcnow

ROLES = ("patient", "doctor", "admin")
VERIFICATION_STATUSES = ("pending", "verified", "rejected")


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    google_sub: Mapped[str] = mapped_column(String(255), unique=True)
    email: Mapped[str] = mapped_column(String(320), index=True)
    name: Mapped[str] = mapped_column(String(200))
    avatar_url: Mapped[str | None] = mapped_column(Text)
    role: Mapped[str | None] = mapped_column(String(20))  # null until onboarding
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    doctor_profile: Mapped["DoctorProfile | None"] = relationship(
        back_populates="user", foreign_keys="DoctorProfile.user_id", lazy="selectin"
    )

    @property
    def onboarded(self) -> bool:
        return self.role is not None


class DoctorProfile(Base):
    __tablename__ = "doctor_profiles"

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    full_name: Mapped[str] = mapped_column(String(200))
    specialty: Mapped[str] = mapped_column(String(100))
    organization: Mapped[str] = mapped_column(String(200))
    council: Mapped[str] = mapped_column(String(200))
    registration_number: Mapped[str] = mapped_column(String(50))
    verification_status: Mapped[str] = mapped_column(String(20), default="pending")
    verified_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    review_note: Mapped[str | None] = mapped_column(Text)
    fhir_practitioner_id: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    user: Mapped[User] = relationship(back_populates="doctor_profile", foreign_keys=[user_id])

    @property
    def is_verified(self) -> bool:
        return self.verification_status == "verified"
