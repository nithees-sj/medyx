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
    from app.services.mirror import mirror_audit

    # Mirrored after the caller's commit (the background task opens its own session).
    _after_commit(db, lambda: mirror_audit(ev.id))
    return ev


def _after_commit(db: AsyncSession, fn) -> None:
    from sqlalchemy import event

    def run(_session) -> None:
        fn()

    event.listen(db.sync_session, "after_commit", run, once=True)


_recent_views: dict[tuple[str, str, str], float] = {}


async def audit_view(db: AsyncSession, access: Any, what: str, scopes: list[str], ip: str | None = None) -> None:
    """Record a doctor's view of part of a record (owners viewing their own data aren't audited).

    Repeated views of the same section by the same doctor within 10 minutes are collapsed,
    so polling and tab switches don't flood the patient's access log.
    """
    import time

    if access.is_owner:
        return
    key = (str(access.user.id), str(access.profile.id), what)
    now = time.monotonic()
    if now - _recent_views.get(key, -1e9) < 600:
        return
    _recent_views[key] = now
    await log_event(
        db,
        profile_id=access.profile.id,
        actor_user_id=access.user.id,
        actor_label=access.actor_label,
        action="view",
        scopes=scopes,
        details={"section": what},
        ip=ip,
    )
    await db.commit()
