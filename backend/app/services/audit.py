"""Audit log: every clinical access by someone other than the owner, every emergency view,
every upload/prescription/consent change. Mirrored to HAPI as FHIR AuditEvent."""

import logging
import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AuditEvent

log = logging.getLogger(__name__)


async def log_event(
    db: AsyncSession,
    *,
    profile_id: uuid.UUID | None,
    actor_user_id: uuid.UUID | None,
    actor_label: str,
    action: str,
    scopes: list[str] | None = None,
    details: dict[str, Any] | None = None,
    ip: str | None = None,
) -> AuditEvent:
    ev = AuditEvent(
        profile_id=profile_id,
        actor_user_id=actor_user_id,
        actor_label=actor_label,
        action=action,
        scopes_touched=sorted(scopes or []),
        details=details or {},
        ip=ip,
    )
    db.add(ev)
    await db.flush()
    return ev
