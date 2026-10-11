"""Doctor verification: run the checks, apply the decision, re-check verified doctors, suspend.

Every status change goes through approve / reject / suspend / reinstate here, whether an admin
or the rules made it, so notifications, FHIR Practitioner creation, consent revocation and
system events are always consistent.
"""

import asyncio
import logging
import uuid
from datetime import timedelta
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai import client as ai
from app.config import get_settings
from app.db import SessionLocal, utcnow
from app.models import Consent, DoctorDocument, DoctorProfile, HealthProfile, User, VerificationCheck
from app.services import fhir_resources, telemetry
from app.services.audit import log_event
from app.services.fhir_client import get_fhir
from app.services.mirror import mirror_consent
from app.services.notifications import notify, notify_admins
from app.services.verification import checks as c
from app.services.verification.certificate import read_certificate
from app.services.verification.policy import Decision, decide
from app.services.verification.registry import get_provider

log = logging.getLogger(__name__)
SYSTEM_ACTOR = "HealthThread doctor verification"

_tasks: set[asyncio.Task] = set()


def _spawn(coro) -> None:
    try:
        task = asyncio.get_running_loop().create_task(coro)
    except RuntimeError:
        coro.close()
        return
    _tasks.add(task)
    task.add_done_callback(_tasks.discard)


# ───────────────────────────── running the checks ─────────────────────────────


async def collect(db: AsyncSession, user: User, dp: DoctorProfile) -> list[c.CheckResult]:
    return [
        c.format_check(dp),
        await c.duplicate_check(db, dp),
        await c.registry_check(dp, get_provider()),
        await c.identity_check(db, user, dp),
        await c.document_check(db, dp),
    ]


async def run(db: AsyncSession, user_id: uuid.UUID, *, trigger: str) -> Decision | None:
    """Collect evidence, store it, and — for pending doctors — act on the decision."""
    dp = await db.get(DoctorProfile, user_id)
    user = await db.get(User, user_id)
    if dp is None or user is None:
        return None
    results = await collect(db, user, dp)
    s = get_settings()
    decision = decide(results, auto_approve=s.verification_auto_approve, auto_reject=s.verification_auto_reject)
    run_id = uuid.uuid4()
    for r in results:
        db.add(
            VerificationCheck(
                run_id=run_id,
                doctor_user_id=user_id,
                kind=r.kind,
                status=r.status,
                provider=r.provider,
                summary=r.summary,
                details=r.details,
            )
        )
    dp.last_checked_at = utcnow()
    dp.verification_summary = {
        "run_id": str(run_id),
        "decision": decision.action,
        "risk": decision.risk,
        "reasons": decision.reasons,
        "trigger": trigger,
        "ran_at": utcnow().isoformat(),
        "checks": {r.kind: r.status for r in results},
    }
    if dp.verification_status == "pending":
        if decision.action == "approve":
            await approve(db, dp, by=None, method="automatic")
        elif decision.action == "reject":
            await reject(db, dp, by=None, method="automatic", note=decision.doctor_message or decision.reasons[0])
        elif decision.risk == "high":
            await notify_admins(
                db,
                "doctor_high_risk",
                f"Check {dp.full_name}'s application carefully",
                decision.reasons[0],
                "/admin/doctors",
            )
            telemetry.event(
                "verification_flagged",
                f"{dp.full_name}: high-risk application — {decision.reasons[0]}",
                severity="warning",
                user_id=user_id,
                details={"risk": decision.risk},
            )
    await db.commit()
    log.info("verification run for %s (%s): %s/%s", user_id, trigger, decision.action, decision.risk)
    return decision


async def run_in_new_session(user_id: uuid.UUID, trigger: str) -> None:
    try:
        async with SessionLocal() as db:
            await run(db, user_id, trigger=trigger)
    except Exception:
        log.exception("verification run failed for %s", user_id)
        telemetry.event("job_failed", "A doctor verification run failed", severity="error", user_id=user_id)


def schedule(user_id: uuid.UUID, trigger: str) -> None:
    _spawn(run_in_new_session(user_id, trigger))


async def process_certificate(doc_id: uuid.UUID) -> None:
    """Read an uploaded certificate with the AI, store the fields, then re-run the checks."""
    async with SessionLocal() as db:
        doc = await db.get(DoctorDocument, doc_id)
        if doc is None:
            return
        try:
            fields = await read_certificate(Path(doc.storage_path).read_bytes(), doc.mime)
            doc.extracted = fields.model_dump(mode="json")
        except ai.AIError as e:
            doc.extracted = {"error": str(e)}
        await db.commit()
        await run(db, doc.doctor_user_id, trigger="certificate")


def schedule_certificate(doc_id: uuid.UUID) -> None:
    _spawn(process_certificate(doc_id))


# ───────────────────────────── status changes ─────────────────────────────


def _label(by: User | None) -> str:
    return by.name if by else "automatic checks"


def _next_check() -> Any:
    return utcnow() + timedelta(days=get_settings().verification_recheck_days) if get_provider() else None


async def approve(
    db: AsyncSession, dp: DoctorProfile, *, by: User | None, method: str, note: str | None = None
) -> None:
    dp.verification_status = "verified"
    dp.verification_method = method
    dp.review_note = note
    dp.verified_by = by.id if by else None
    dp.verified_at = utcnow()
    dp.next_check_at = _next_check()
    if not dp.fhir_practitioner_id:
        created = await get_fhir().create(
            fhir_resources.practitioner(
                full_name=dp.full_name,
                specialty=dp.specialty,
                council=dp.council,
                registration_number=dp.registration_number,
                organization=dp.organization,
            )
        )
        dp.fhir_practitioner_id = created["id"]
    await notify(
        db, dp.user_id, "doctor_verified", "Your account is verified", "You can now accept patient shares.", "/doctor"
    )
    telemetry.event(
        "doctor_verified",
        f"{dp.full_name} verified by {_label(by)}",
        user_id=dp.user_id,
        details={"method": method, "by": str(by.id) if by else None},
    )


async def reject(db: AsyncSession, dp: DoctorProfile, *, by: User | None, method: str, note: str) -> None:
    dp.verification_status = "rejected"
    dp.verification_method = method
    dp.review_note = note
    dp.verified_by = by.id if by else None
    dp.verified_at = utcnow()
    dp.next_check_at = None
    await notify(db, dp.user_id, "doctor_rejected", "Verification was not approved", note, "/doctor/profile")
    telemetry.event(
        "doctor_rejected",
        f"{dp.full_name} rejected by {_label(by)}",
        severity="warning",
        user_id=dp.user_id,
        details={"method": method, "by": str(by.id) if by else None},
    )


async def suspend(db: AsyncSession, dp: DoctorProfile, *, by: User | None, reason: str, method: str) -> int:
    """Block the doctor and end every active share they hold. Returns how many shares ended."""
    dp.verification_status = "suspended"
    dp.verification_method = method
    dp.review_note = reason
    dp.next_check_at = None
    active = (
        await db.scalars(select(Consent).where(Consent.doctor_user_id == dp.user_id, Consent.status == "active"))
    ).all()
    for consent in active:
        consent.status = "revoked"
        consent.revoked_at = utcnow()
        profile = await db.get(HealthProfile, consent.profile_id)
        await log_event(
            db,
            profile_id=consent.profile_id,
            actor_user_id=by.id if by else None,
            actor_label=SYSTEM_ACTOR,
            action="consent_change",
            scopes=list(consent.scopes),
            details={"event": "revoked", "reason": "doctor_suspended"},
        )
        if profile:
            await notify(
                db,
                profile.owner_user_id,
                "access_revoked",
                f"{dp.full_name}'s access to {profile.display_name}'s record has ended",
                "HealthThread suspended this doctor's account while their registration is checked.",
                f"/app/p/{profile.id}/sharing",
            )
        mirror_consent(consent.id)
    await notify(db, dp.user_id, "doctor_suspended", "Your account is suspended", reason, "/doctor/profile")
    if by is None:
        await notify_admins(
            db, "doctor_suspended", f"{dp.full_name} was suspended automatically", reason, "/admin/doctors"
        )
    telemetry.event(
        "doctor_suspended",
        f"{dp.full_name} suspended by {_label(by)}; {len(active)} active share(s) ended",
        severity="warning",
        user_id=dp.user_id,
        details={"method": method, "shares_ended": len(active)},
    )
    return len(active)


async def reinstate(db: AsyncSession, dp: DoctorProfile, *, by: User, note: str | None) -> None:
    await approve(db, dp, by=by, method="admin", note=note)
    telemetry.event("doctor_reinstated", f"{dp.full_name} reinstated by {by.name}", user_id=dp.user_id)


# ───────────────────────────── periodic re-check ─────────────────────────────


async def recheck_due() -> str:
    """Re-query the register for verified doctors whose next check is due. A registration that
    disappears or stops being active suspends the doctor; register outages decide nothing."""
    provider = get_provider()
    if provider is None:
        return "skipped: no register connection configured"
    checked = suspended = errors = 0
    async with SessionLocal() as db:
        due = (
            await db.scalars(
                select(DoctorProfile).where(
                    DoctorProfile.verification_status == "verified",
                    (DoctorProfile.next_check_at.is_(None)) | (DoctorProfile.next_check_at <= utcnow()),
                )
            )
        ).all()
        for dp in due:
            result = await c.registry_check(dp, provider)
            checked += 1
            dp.last_checked_at = utcnow()
            db.add(
                VerificationCheck(
                    run_id=uuid.uuid4(),
                    doctor_user_id=dp.user_id,
                    kind="registry",
                    status=result.status,
                    provider=result.provider,
                    summary=result.summary,
                    details={**result.details, "trigger": "recheck"},
                )
            )
            if result.status == "failed" and result.details.get("reason") in ("not_found", "inactive"):
                await suspend(
                    db, dp, by=None, reason=f"Periodic register check: {result.summary}", method="registry recheck"
                )
                suspended += 1
            elif result.status == "error":
                errors += 1
                dp.next_check_at = utcnow() + timedelta(days=1)
            else:
                dp.next_check_at = _next_check()
        await db.commit()
    return f"checked {checked}, suspended {suspended}, register errors {errors}"
