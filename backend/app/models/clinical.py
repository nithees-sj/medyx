"""Alerts, consents, audit, emergency cards, chat, notes, notifications, summary cache."""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base, utcnow

ALERT_TYPES = ("duplicate_therapy", "allergy_conflict", "prescribing_cascade", "lab_drift", "interaction")
ALERT_STATUSES = ("active", "reviewed_intentional", "resolved", "dismissed")
CONSENT_STATUSES = ("pending_claim", "requested", "active", "revoked", "expired", "denied")
SCOPES = ("conditions", "medications", "allergies", "labs", "documents", "notes", "mental_health")
AUDIT_ACTIONS = (
    "view",
    "upload",
    "prescribe",
    "chat",
    "summary",
    "export",
    "emergency_view",
    "consent_change",
    "alert_review",
)


class Alert(Base):
    __tablename__ = "alerts"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    profile_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("health_profiles.id", ondelete="CASCADE"), index=True
    )
    rule_id: Mapped[str] = mapped_column(String(80))
    type: Mapped[str] = mapped_column(String(40))
    severity: Mapped[str] = mapped_column(String(20))
    title: Mapped[str] = mapped_column(String(300))
    patient_text: Mapped[str] = mapped_column(Text)
    clinical_text: Mapped[str] = mapped_column(Text)
    evidence: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    details: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    status: Mapped[str] = mapped_column(String(30), default="active")
    reviewed_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    review_note: Mapped[str | None] = mapped_column(Text)
    fingerprint: Mapped[str] = mapped_column(String(64), unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class Consent(Base):
    __tablename__ = "consents"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    profile_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("health_profiles.id", ondelete="CASCADE"), index=True
    )
    granted_by_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    doctor_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), index=True)
    scopes: Mapped[list[str]] = mapped_column(ARRAY(String(30)))
    can_write: Mapped[bool] = mapped_column(Boolean, default=False)
    purpose: Mapped[str | None] = mapped_column(String(300))
    status: Mapped[str] = mapped_column(String(20))
    share_token_hash: Mapped[str | None] = mapped_column(String(64), unique=True)
    claim_deadline: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    duration_hours: Mapped[int] = mapped_column(Integer)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    fhir_consent_id: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AuditEvent(Base):
    __tablename__ = "audit_events"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    profile_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("health_profiles.id", ondelete="CASCADE"), index=True
    )
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    actor_label: Mapped[str] = mapped_column(String(300))
    action: Mapped[str] = mapped_column(String(30))
    scopes_touched: Mapped[list[str]] = mapped_column(ARRAY(String(30)), default=list)
    details: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    ip: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)


class EmergencyCard(Base):
    __tablename__ = "emergency_cards"

    profile_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("health_profiles.id", ondelete="CASCADE"), primary_key=True
    )
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    regenerated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ChatMessage(Base):
    __tablename__ = "chat_messages"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    profile_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("health_profiles.id", ondelete="CASCADE"), index=True
    )
    doctor_user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True)
    role: Mapped[str] = mapped_column(String(20))
    content: Mapped[str] = mapped_column(Text)
    citations: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ClinicalNote(Base):
    __tablename__ = "clinical_notes"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    profile_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("health_profiles.id", ondelete="CASCADE"), index=True
    )
    author_user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    title: Mapped[str] = mapped_column(String(300))
    body: Mapped[str] = mapped_column(Text)
    fhir_document_reference_id: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Notification(Base):
    __tablename__ = "notifications"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    type: Mapped[str] = mapped_column(String(40))
    title: Mapped[str] = mapped_column(String(300))
    body: Mapped[str | None] = mapped_column(Text)
    link: Mapped[str | None] = mapped_column(String(500))
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)


class SummaryCache(Base):
    __tablename__ = "summary_cache"

    profile_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("health_profiles.id", ondelete="CASCADE"), primary_key=True
    )
    specialty: Mapped[str] = mapped_column(String(100), primary_key=True)
    # Scope set is part of the key so a narrower consent never sees a wider cached summary.
    scope_key: Mapped[str] = mapped_column(String(200), primary_key=True)
    record_version: Mapped[int] = mapped_column(Integer)
    content: Mapped[dict[str, Any]] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
