"""Cross-hospital safety engine: deterministic rules → persisted, idempotent alerts."""

import asyncio
import contextlib
import copy
import logging
import re
import uuid
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app import knowledge as kb
from app.ai.client import AIError
from app.db import SessionLocal
from app.models import Alert, HealthProfile
from app.services import record as record_service
from app.services.ingest import normalize as nz
from app.services.record import Medication, PatientRecord
from app.services.safety import explain
from app.services.safety.findings import Finding
from app.services.safety.rules import allergy_conflict, cascade, duplicate_therapy, interaction, lab_drift

log = logging.getLogger(__name__)

RULES = [duplicate_therapy, allergy_conflict, cascade, lab_drift, interaction]
SEVERITY_ORDER = {"critical": 0, "warning": 1, "info": 2}


def today() -> date:
    return date.today()


def run_rules(record: PatientRecord, on: date | None = None) -> list[Finding]:
    on = on or today()
    findings: list[Finding] = []
    for rule in RULES:
        findings.extend(rule.evaluate(record, on))
    findings.sort(key=lambda f: (SEVERITY_ORDER.get(f.severity, 9), f.type))
    return findings


@dataclass
class RunSummary:
    active: int
    created: int
    resolved: int


async def run_for_profile(db: AsyncSession, profile: HealthProfile, on: date | None = None) -> RunSummary:
    """Evaluate all rules and reconcile the alerts table. Safe to call repeatedly."""
    await db.refresh(profile)
    record = await record_service.load_record(db, profile)
    findings = run_rules(record, on)
    explain.apply_templates(findings)

    existing = {a.fingerprint: a for a in (await db.scalars(select(Alert).where(Alert.profile_id == profile.id))).all()}
    seen: set[str] = set()
    created = 0
    new_alerts: list[Alert] = []
    for f in findings:
        fp = f.fingerprint(str(profile.id))
        seen.add(fp)
        alert = existing.get(fp)
        payload = {
            "rule_id": f.rule_id,
            "type": f.type,
            "severity": f.severity,
            "title": f.title,
            "evidence": [e.json() for e in f.evidence],
        }
        if alert is None:
            alert = Alert(
                profile_id=profile.id,
                fingerprint=fp,
                status="active",
                patient_text=f.patient_text,
                clinical_text=f.clinical_text,
                details={**f.details, "facts": f.facts, "explanation_source": "template"},
                **payload,
            )
            db.add(alert)
            new_alerts.append(alert)
            created += 1
        else:
            for k, v in payload.items():
                setattr(alert, k, v)
            keep = (alert.details or {}).get("explanation_source") == "ai"
            alert.details = {
                **f.details,
                "facts": f.facts,
                "explanation_source": "ai" if keep else "template",
            }
            if not keep:
                alert.patient_text, alert.clinical_text = f.patient_text, f.clinical_text
            if alert.status == "resolved":  # fired again after being auto-resolved
                alert.status = "active"
    await db.flush()
    resolved = 0
    for fp, alert in existing.items():
        if fp not in seen and alert.status in ("active", "reviewed_intentional"):
            alert.status = "resolved"
            # When the same problem is re-detected with new evidence (e.g. another lab result arrived),
            # the old alert is superseded rather than "resolved", and hidden from alert lists.
            old_refs = {e["ref"] for e in alert.evidence}
            successor = next(
                (n for n in new_alerts if n.type == alert.type and old_refs & {e["ref"] for e in n.evidence}), None
            )
            if successor is not None:
                alert.details = {**(alert.details or {}), "superseded_by": str(successor.id)}
                alert.review_note = alert.review_note or "Updated with newer evidence."
            else:
                alert.review_note = alert.review_note or "Resolved automatically: no longer detected in the record."
                resolved += 1
    await db.commit()
    schedule_explanations(profile.id)
    statuses = (await db.scalars(select(Alert.status).where(Alert.profile_id == profile.id))).all()
    return RunSummary(active=statuses.count("active"), created=created, resolved=resolved)


async def safety_hook(db: AsyncSession, profile: HealthProfile) -> None:
    """Registered as an ingest post-write hook."""
    try:
        await run_for_profile(db, profile)
    except Exception:
        log.exception("safety run failed for profile %s", profile.id)


# ─────────────────────────────── AI explanations (debounced, batched) ───────────────────────────────

_pending: dict[uuid.UUID, asyncio.Task] = {}
EXPLAIN_DELAY_SECONDS = 4.0


def schedule_explanations(profile_id: uuid.UUID, delay: float | None = None) -> None:
    """Upgrade template explanations with one AI call once writes for this profile settle."""
    task = _pending.get(profile_id)
    if task and not task.done():
        task.cancel()
    with contextlib.suppress(RuntimeError):  # no running loop (e.g. one-off scripts)
        _pending[profile_id] = asyncio.get_running_loop().create_task(
            _explain_later(profile_id, EXPLAIN_DELAY_SECONDS if delay is None else delay)
        )


async def _explain_later(profile_id: uuid.UUID, delay: float) -> None:
    await asyncio.sleep(delay)
    try:
        await explain_pending(profile_id)
    except Exception:
        log.exception("explanations failed for profile %s", profile_id)


async def explain_pending(profile_id: uuid.UUID) -> int:
    async with SessionLocal() as db:
        alerts = (
            await db.scalars(
                select(Alert).where(
                    Alert.profile_id == profile_id, Alert.status.in_(["active", "reviewed_intentional"])
                )
            )
        ).all()
        todo = [a for a in alerts if (a.details or {}).get("explanation_source") != "ai"]
        if not todo:
            return 0
        items = [
            {
                "key": str(a.id),
                "type": a.type,
                "severity": a.severity,
                "title": a.title,
                "facts": (a.details or {}).get("facts", {}),
            }
            for a in todo
        ]
        try:
            texts = await explain.ai_explanations(items)
        except AIError as err:
            log.info("AI explanations unavailable (%s); keeping template text", err)
            return 0
        for a in todo:
            text = texts.get(str(a.id))
            if not text:
                continue
            a.patient_text = explain.ensure_disclaimer(text.patient_text)
            a.clinical_text = text.clinical_text.strip()
            a.details = {**(a.details or {}), "explanation_source": "ai"}
        await db.commit()
        return len(texts)


# ─────────────────────────────── prescribe-time check ───────────────────────────────


def draft_medication(
    drug: str, strength: str | None, frequency: str | None, duration_days: int | None, org: str | None, on: date
) -> Medication:
    info = kb.resolve_drug(brand=drug, generic_from_ai=drug, written_text=drug)
    if not strength:
        m = re.search(r"(\d+(?:\.\d+)?\s*(?:mg|mcg|g|ml))", drug, flags=re.I)
        strength = m.group(1) if m else None
    mg = nz.strength_mg(strength)
    freq = nz.parse_frequency(frequency) or {"morning": 0, "afternoon": 0, "night": 0, "per_day": 0, "as_needed": False}
    end = on + timedelta(days=duration_days - 1) if duration_days else None
    return Medication(
        ref="MedicationRequest/draft",
        generic=info.generic,
        display=" ".join(x for x in [info.generic.title(), strength] if x),
        brand=info.brand,
        classes=kb.classes_for(info.generic, mg),
        strength=strength,
        strength_mg=mg,
        frequency_label=nz.frequency_label(freq),
        frequency_text=frequency,
        per_day=freq["per_day"],
        as_needed=freq["as_needed"],
        instructions=None,
        start=on,
        end=end,
        fhir_status="active",
        org=org,
        requester=None,
        written_text=drug,
    )


def check_draft(record: PatientRecord, draft: Medication, on: date | None = None) -> list[Finding]:
    """Alerts that would fire if the draft were prescribed (only those involving the draft)."""
    on = on or today()
    trial = copy.copy(record)
    trial.medications = [*record.medications, draft]
    findings = [f for f in run_rules(trial, on) if any(e.ref == draft.ref for e in f.evidence)]
    explain.apply_templates(findings)
    return findings


def alert_json(a: Alert) -> dict[str, Any]:
    details = dict(a.details or {})
    details.pop("facts", None)
    return {
        "id": str(a.id),
        "rule_id": a.rule_id,
        "type": a.type,
        "severity": a.severity,
        "title": a.title,
        "patient_text": a.patient_text,
        "clinical_text": a.clinical_text,
        "evidence": a.evidence,
        "status": a.status,
        "review_note": a.review_note,
        "reviewed_by": str(a.reviewed_by) if a.reviewed_by else None,
        "details": details,
        "created_at": a.created_at.isoformat(),
        "updated_at": a.updated_at.isoformat(),
    }
