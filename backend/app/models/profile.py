import uuid
from datetime import date, datetime

from sqlalchemy import Date, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base, utcnow

RELATIONSHIPS = ("self", "parent", "child", "spouse", "other")
SEXES = ("male", "female", "other", "unknown")
BLOOD_GROUPS = ("A+", "A-", "B+", "B-", "AB+", "AB-", "O+", "O-", "unknown")


class HealthProfile(Base):
    """One person's health record. An account (owner) can manage several (self + dependents)."""

    __tablename__ = "health_profiles"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    owner_user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    display_name: Mapped[str] = mapped_column(String(200))
    relationship: Mapped[str] = mapped_column(String(20))
    fhir_patient_id: Mapped[str | None] = mapped_column(String(64))
    dob: Mapped[date] = mapped_column(Date)
    sex: Mapped[str] = mapped_column(String(10))
    blood_group: Mapped[str] = mapped_column(String(10), default="unknown")
    emergency_contact_name: Mapped[str | None] = mapped_column(String(200))
    emergency_contact_phone: Mapped[str | None] = mapped_column(String(40))
    healththread_id: Mapped[str] = mapped_column(String(20), unique=True)
    record_version: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
