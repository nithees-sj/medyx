"""Admin monitoring: what is happening across the platform — without seeing anyone's health data.

Privacy boundary (spec §3: admins have no clinical data access):
- Patients appear only as their pseudonymous HealthThread ID, never by profile name.
- Audit details pass through an allow-list: document labels (D3), scope categories, share
  durations, alert statuses. Medicine names, alert titles, questions, notes, file names and
  free-text purposes are dropped.
- Telemetry has no bodies, prompts or answers to begin with (services/telemetry.py).
"""

import re
import uuid
from datetime import date, datetime, timedelta
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import Float, and_, cast, func, or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai import client as ai_client
from app.config import get_settings
from app.db import get_db, utcnow
from app.deps import require_admin
from app.models import (
    AICall,
    Alert,
    AuditEvent,
    Consent,
    DoctorProfile,
    Document,
    EmergencyCard,
    HealthProfile,
    RequestLog,
    SystemEvent,
    User,
)
from app.models.clinical import ALERT_STATUSES
from app.services import telemetry
from app.services.fhir_client import get_fhir
from app.services.ingest.pipeline import worker
from app.services.verification import registry

router = APIRouter(prefix="/admin", tags=["monitoring"])

RECORD_CATEGORY = {
    "view": "clinical_access",
    "chat": "clinical_access",
    "summary": "clinical_access",
    "export": "clinical_access",
    "upload": "record_change",
    "prescribe": "record_change",
    "alert_review": "record_change",
    "consent_change": "sharing",
    "emergency_view": "emergency",
}
SYSTEM_CATEGORY = {
    "login": "auth",
    "logout": "auth",
    "onboarded": "auth",
    "login_failed": "security",
    "access_denied": "security",
    "rate_limited": "security",
    "invalid_token": "security",
    "server_error": "errors",
    "job_failed": "errors",
    "document_failed": "errors",
    "document_retried": "errors",
}
CATEGORIES = ("clinical_access", "record_change", "sharing", "emergency", "auth", "security", "verification", "errors")
_DOCTOR_ACCESS_ACTIONS = ("view", "chat", "summary", "export", "prescribe")
# Sections written by audit_view() and the copilot — fixed strings from our own code.
_SAFE_SECTIONS = {"alerts", "timeline", "trends", "medications", "documents", "panel insights", "summary", "notes"}
_SHARE_EVENTS = {
    "share_created": "created a QR share",
    "share_claimed": "claimed a QR share",
    "access_requested": "requested access",
    "request_approved": "approved an access request",
    "request_denied": "declined an access request",
    "revoked": "ended a share",
}


def _since(hours: int) -> datetime:
    return utcnow() - timedelta(hours=hours)


def _local_day(col: Any) -> Any:
    return func.date(func.timezone(get_settings().default_timezone, col))


def _system_category(kind: str) -> str:
    if kind in SYSTEM_CATEGORY:
        return SYSTEM_CATEGORY[kind]
    if kind.startswith(("doctor_", "trusted_domain_", "verification_")):
        return "verification"
    return "errors" if kind.endswith("_failed") else "auth"


def record_summary(action: str, details: dict[str, Any], scopes: list[str]) -> str:
    """A human sentence for an audit event, built only from allow-listed, non-clinical fields."""
    d = details or {}
    if action == "view":
        section = d.get("section") if d.get("section") in _SAFE_SECTIONS else "the record"
        text_ = f"viewed {section}"
    elif action == "chat":
        text_ = "asked the copilot a question"
    elif action == "summary":
        text_ = "opened a specialty summary" + (" (cached)" if d.get("cached") else "")
    elif action == "export":
        text_ = "exported the record as a FHIR bundle"
    elif action == "upload":
        label = d.get("document")
        text_ = (
            f"uploaded document {label}"
            if isinstance(label, str) and re.fullmatch(r"D\d+", label)
            else "uploaded a document"
        )
    elif action == "prescribe":
        text_ = "issued a prescription" + (" — overriding a critical safety alert" if d.get("override_reason") else "")
    elif action == "alert_review":
        st = d.get("status")
        text_ = (
            f"marked a safety alert as {st.replace('_', ' ')}" if st in ALERT_STATUSES else "reviewed a safety alert"
        )
    elif action == "consent_change":
        text_ = _SHARE_EVENTS.get(d.get("event", ""), "changed sharing")
        if isinstance(d.get("duration"), str) and len(d["duration"]) < 20:
            text_ += f" for {d['duration']}"
        if d.get("reason") == "doctor_suspended":
            text_ += " (doctor suspended)"
    elif action == "emergency_view":
        text_ = "opened the emergency card"
    else:
        text_ = action.replace("_", " ")
    if scopes and action in ("view", "consent_change", "chat"):
        text_ += " · " + ", ".join(s.replace("_", " ") for s in scopes)
    return text_


def _sanitize_doc_error(err: str | None) -> str | None:
    if not err:
        return None
    if err.startswith("Couldn't read this document") or err.startswith("Something went wrong"):
        return err[:200]  # AI error messages are fixed, content-free strings
    m = re.match(r"FHIR (\d{3})", err)
    if m:
        return f"The FHIR server rejected the write (HTTP {m.group(1)})"
    return "Processing error"


# ───────────────────────────── overview ─────────────────────────────


@router.get("/overview")
async def overview(_: User = Depends(require_admin), db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    day = _since(24)
    users_by_role = {
        (r or "not_onboarded"): n
        for r, n in (await db.execute(select(User.role, func.count()).group_by(User.role))).all()
    }
    doctors = dict(
        (
            await db.execute(
                select(DoctorProfile.verification_status, func.count()).group_by(DoctorProfile.verification_status)
            )
        ).all()
    )
    high_risk = await db.scalar(
        select(func.count())
        .select_from(DoctorProfile)
        .where(
            DoctorProfile.verification_status == "pending",
            DoctorProfile.verification_summary["risk"].astext == "high",
        )
    )
    not_superseded = Alert.details["superseded_by"].astext.is_(None)
    active_alerts = and_(Alert.status == "active", or_(Alert.details.is_(None), not_superseded))
    docs_by_status = dict((await db.execute(select(Document.status, func.count()).group_by(Document.status))).all())

    async def count(model: Any, *where: Any) -> int:
        return int(await db.scalar(select(func.count()).select_from(model).where(*where)) or 0)

    doctor_actor = AuditEvent.actor_user_id.in_(select(User.id).where(User.role == "doctor"))
    last_24h = {
        "sign_ins": await count(SystemEvent, SystemEvent.kind == "login", SystemEvent.created_at >= day),
        "failed_sign_ins": await count(SystemEvent, SystemEvent.kind == "login_failed", SystemEvent.created_at >= day),
        "active_users": int(
            await db.scalar(
                select(func.count(func.distinct(RequestLog.user_id))).where(
                    RequestLog.created_at >= day, RequestLog.user_id.is_not(None)
                )
            )
            or 0
        ),
        "uploads": await count(Document, Document.created_at >= day),
        "doctor_record_access": await count(
            AuditEvent, AuditEvent.created_at >= day, AuditEvent.action.in_(_DOCTOR_ACCESS_ACTIONS), doctor_actor
        ),
        "requests": await count(RequestLog, RequestLog.created_at >= day),
        "server_errors": await count(RequestLog, RequestLog.created_at >= day, RequestLog.status >= 500),
        "access_denied": await count(SystemEvent, SystemEvent.kind == "access_denied", SystemEvent.created_at >= day),
        "ai_calls": await count(AICall, AICall.created_at >= day),
        "ai_failures": await count(AICall, AICall.created_at >= day, AICall.ok.is_(False)),
        "emergency_views": await count(AuditEvent, AuditEvent.action == "emergency_view", AuditEvent.created_at >= day),
        "critical_overrides": await count(
            AuditEvent,
            AuditEvent.action == "prescribe",
            AuditEvent.created_at >= day,
            AuditEvent.details["override_reason"].astext.is_not(None),
        ),
    }
    kpis = {
        "users": sum(users_by_role.values()),
        "users_by_role": users_by_role,
        "doctors": doctors,
        "profiles": await count(HealthProfile),
        "documents": sum(docs_by_status.values()),
        "documents_by_status": docs_by_status,
        "active_consents": await count(Consent, Consent.status == "active"),
        "active_alerts": await count(Alert, active_alerts),
        "critical_alerts": await count(Alert, active_alerts, Alert.severity == "critical"),
        "alerts_by_type": dict(
            (await db.execute(select(Alert.type, func.count()).where(active_alerts).group_by(Alert.type))).all()
        ),
    }

    attention: list[dict[str, Any]] = []

    def flag(kind: str, severity: str, title: str, n: int, link: str) -> None:
        if n:
            attention.append({"kind": kind, "severity": severity, "title": title, "count": n, "link": link})

    flag("doctors_high_risk", "critical", "High-risk doctor applications", int(high_risk or 0), "/admin/doctors")
    flag("doctors_pending", "warning", "Doctors waiting for review", doctors.get("pending", 0), "/admin/doctors")
    flag("server_errors", "critical", "Server errors in the last 24 h", last_24h["server_errors"], "/admin/system")
    flag(
        "failed_documents",
        "warning",
        "Documents that failed to process",
        docs_by_status.get("failed", 0),
        "/admin/system",
    )
    if last_24h["ai_calls"] and last_24h["ai_failures"] / last_24h["ai_calls"] >= 0.2:
        flag("ai_failures", "warning", "AI calls failing (≥ 20% in 24 h)", last_24h["ai_failures"], "/admin/system")
    flag("access_denied", "info", "Access denials in the last 24 h", last_24h["access_denied"], "/admin/activity")
    flag(
        "failed_sign_ins", "warning", "Failed sign-ins in the last 24 h", last_24h["failed_sign_ins"], "/admin/activity"
    )
    flag(
        "critical_overrides",
        "info",
        "Critical safety alerts overridden at prescribing (24 h)",
        last_24h["critical_overrides"],
        "/admin/activity",
    )  # noqa: E501
    flag("doctors_suspended", "info", "Suspended doctors", doctors.get("suspended", 0), "/admin/doctors")

    return {"kpis": kpis, "last_24h": last_24h, "attention": attention, "daily": await _daily(db, 14)}


async def _daily(db: AsyncSession, days: int) -> list[dict[str, Any]]:
    start = utcnow() - timedelta(days=days - 1)
    series = {
        "sign_ins": select(_local_day(SystemEvent.created_at), func.count()).where(
            SystemEvent.kind == "login", SystemEvent.created_at >= start - timedelta(days=1)
        ),
        "uploads": select(_local_day(Document.created_at), func.count()).where(
            Document.created_at >= start - timedelta(days=1)
        ),
        "doctor_access": select(_local_day(AuditEvent.created_at), func.count()).where(
            AuditEvent.created_at >= start - timedelta(days=1),
            AuditEvent.action.in_(_DOCTOR_ACCESS_ACTIONS),
            AuditEvent.actor_user_id.in_(select(User.id).where(User.role == "doctor")),
        ),
        "ai_calls": select(_local_day(AICall.created_at), func.count()).where(
            AICall.created_at >= start - timedelta(days=1)
        ),
    }
    values: dict[str, dict[date, int]] = {}
    for name, q in series.items():
        first_col = q.selected_columns[0]
        values[name] = {d: n for d, n in (await db.execute(q.group_by(first_col))).all()}
    today = (await db.scalar(select(_local_day(func.now())))) or date.today()
    out = []
    for i in range(days - 1, -1, -1):
        d = today - timedelta(days=i)
        out.append({"date": d.isoformat(), **{k: v.get(d, 0) for k, v in values.items()}})
    return out


# ───────────────────────────── activity feed ─────────────────────────────


@router.get("/activity")
async def activity(
    source: Literal["all", "record", "system"] = "all",
    category: str | None = None,
    severity: Literal["info", "warning", "error"] | None = None,
    before: datetime | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    _: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    if category and category not in CATEGORIES:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Unknown category")
    items: list[dict[str, Any]] = []
    record_cats = {k for k, v in RECORD_CATEGORY.items() if category in (None, v)}
    if source in ("all", "record") and record_cats and severity in (None, "info", "warning"):
        q = (
            select(AuditEvent, HealthProfile.healththread_id, User.role)
            .outerjoin(HealthProfile, HealthProfile.id == AuditEvent.profile_id)
            .outerjoin(User, User.id == AuditEvent.actor_user_id)
            .where(AuditEvent.action.in_(record_cats))
        )
        if severity == "warning":
            q = q.where(AuditEvent.action == "emergency_view")
        if before:
            q = q.where(AuditEvent.created_at < before)
        for ev, ht_id, role in (await db.execute(q.order_by(AuditEvent.created_at.desc()).limit(limit))).all():
            items.append(
                {
                    "id": str(ev.id),
                    "at": ev.created_at,
                    "source": "record",
                    "category": RECORD_CATEGORY.get(ev.action, "clinical_access"),
                    "kind": ev.action,
                    "severity": "warning" if ev.action == "emergency_view" else "info",
                    "actor": ev.actor_label,
                    "actor_role": role or ("public" if ev.action == "emergency_view" else "system"),
                    "target": ht_id,
                    "summary": record_summary(ev.action, ev.details, list(ev.scopes_touched or [])),
                    "ip": ev.ip,
                }
            )
    if source in ("all", "system"):
        sq = select(SystemEvent, User.name, User.role).outerjoin(User, User.id == SystemEvent.user_id)
        if severity:
            sq = sq.where(SystemEvent.severity == severity)
        if before:
            sq = sq.where(SystemEvent.created_at < before)
        rows = (
            await db.execute(sq.order_by(SystemEvent.created_at.desc()).limit(limit * 3 if category else limit))
        ).all()
        for se, name, role in rows:
            cat = _system_category(se.kind)
            if category and cat != category:
                continue
            items.append(
                {
                    "id": str(se.id),
                    "at": se.created_at,
                    "source": "system",
                    "category": cat,
                    "kind": se.kind,
                    "severity": se.severity,
                    "actor": name or ("anonymous" if se.ip else "HealthThread"),
                    "actor_role": role,
                    "target": None,
                    "summary": se.message,
                    "ip": se.ip,
                }
            )
    items.sort(key=lambda x: x["at"], reverse=True)
    items = items[:limit]
    return {"items": items, "next_before": items[-1]["at"] if len(items) == limit else None}


# ───────────────────────────── API traffic ─────────────────────────────


@router.get("/requests")
async def request_metrics(
    hours: int = Query(default=24, ge=1, le=24 * 30),
    _: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    since = _since(hours)
    window = RequestLog.created_at >= since
    p50 = func.percentile_cont(0.5).within_group(RequestLog.duration_ms)
    p95 = func.percentile_cont(0.95).within_group(RequestLog.duration_ms)
    err5 = func.count().filter(RequestLog.status >= 500)
    err4 = func.count().filter(and_(RequestLog.status >= 400, RequestLog.status < 500))
    tot = (await db.execute(select(func.count(), err4, err5, p50, p95).where(window))).one()
    bucket = func.date_trunc("hour" if hours <= 72 else "day", RequestLog.created_at)
    series = (
        await db.execute(select(bucket, func.count(), err4, err5).where(window).group_by(bucket).order_by(bucket))
    ).all()
    routes = (
        await db.execute(
            select(
                RequestLog.method,
                RequestLog.route,
                func.count(),
                err4,
                err5,
                p50,
                p95,
                func.max(RequestLog.duration_ms),
            )
            .where(window)
            .group_by(RequestLog.method, RequestLog.route)
            .order_by(func.count().desc())
            .limit(40)
        )
    ).all()
    errors = (
        await db.scalars(
            select(RequestLog).where(window, RequestLog.status >= 500).order_by(RequestLog.created_at.desc()).limit(25)
        )
    ).all()
    return {
        "hours": hours,
        "totals": {
            "requests": tot[0],
            "client_errors": tot[1],
            "server_errors": tot[2],
            "p50_ms": round(tot[3] or 0),
            "p95_ms": round(tot[4] or 0),
        },
        "series": [{"at": t, "requests": n, "client_errors": e4, "server_errors": e5} for t, n, e4, e5 in series],
        "routes": [
            {
                "method": m,
                "route": r,
                "requests": n,
                "client_errors": e4,
                "server_errors": e5,
                "p50_ms": round(a or 0),
                "p95_ms": round(b or 0),
                "max_ms": mx,
            }
            for m, r, n, e4, e5, a, b, mx in routes
        ],
        "recent_errors": [
            {
                "at": e.created_at,
                "method": e.method,
                "route": e.route,
                "status": e.status,
                "error": e.error,
                "role": e.role,
            }
            for e in errors
        ],
    }


# ───────────────────────────── AI usage ─────────────────────────────


@router.get("/ai")
async def ai_metrics(
    hours: int = Query(default=24, ge=1, le=24 * 30),
    _: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    window = AICall.created_at >= _since(hours)
    fails = func.count().filter(AICall.ok.is_(False))
    quota = func.count().filter(AICall.error.in_(["HTTP 429", "HTTP 503"]))
    avg_ms = func.avg(cast(AICall.duration_ms, Float)).filter(AICall.ok.is_(True))
    tok_in, tok_out = func.coalesce(func.sum(AICall.input_tokens), 0), func.coalesce(func.sum(AICall.output_tokens), 0)
    tot = (await db.execute(select(func.count(), fails, quota, avg_ms, tok_in, tok_out).where(window))).one()

    async def grouped(col: Any) -> list[dict[str, Any]]:
        rows = (
            await db.execute(
                select(col, func.count(), fails, quota, avg_ms, tok_in, tok_out)
                .where(window)
                .group_by(col)
                .order_by(func.count().desc())
            )
        ).all()
        return [
            {
                "key": k,
                "calls": n,
                "failures": f,
                "rate_limited": q,
                "avg_ms": round(a or 0),
                "input_tokens": ti,
                "output_tokens": to,
            }  # fmt: skip
            for k, n, f, q, a, ti, to in rows
        ]

    recent = (await db.scalars(select(AICall).order_by(AICall.created_at.desc()).limit(40))).all()
    s = get_settings()
    return {
        "hours": hours,
        "config": {
            "configured": bool(s.gemini_api_key),
            "model": s.gemini_model,
            "fallback_model": s.gemini_fallback_model or None,
            "requests_per_minute": s.ai_requests_per_minute,
            "calls_last_minute": ai_client.calls_in_last_minute(),
        },
        "totals": {
            "calls": tot[0],
            "failures": tot[1],
            "rate_limited": tot[2],
            "avg_ms": round(tot[3] or 0),
            "input_tokens": tot[4],
            "output_tokens": tot[5],
        },
        "by_purpose": await grouped(AICall.purpose),
        "by_model": await grouped(AICall.model),
        "recent": [
            {
                "at": r.created_at,
                "purpose": r.purpose,
                "model": r.model,
                "ok": r.ok,
                "ms": r.duration_ms,
                "input_tokens": r.input_tokens,
                "output_tokens": r.output_tokens,
                "error": r.error,
            }
            for r in recent
        ],
    }


# ───────────────────────────── ingest pipeline ─────────────────────────────


@router.get("/pipeline")
async def pipeline_metrics(_: User = Depends(require_admin), db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    by_status = dict((await db.execute(select(Document.status, func.count()).group_by(Document.status))).all())
    avg_seconds = await db.scalar(
        select(func.avg(func.extract("epoch", Document.updated_at - Document.created_at))).where(
            Document.status.in_(["done", "needs_review"]), Document.created_at >= _since(24)
        )
    )
    failed = (
        await db.execute(
            select(Document, HealthProfile.healththread_id)
            .join(HealthProfile, HealthProfile.id == Document.profile_id)
            .where(Document.status == "failed")
            .order_by(Document.updated_at.desc())
            .limit(50)
        )
    ).all()
    in_flight = (
        await db.execute(
            select(Document.seq, Document.stage, Document.status, Document.created_at, HealthProfile.healththread_id)
            .join(HealthProfile, HealthProfile.id == Document.profile_id)
            .where(Document.status.in_(["queued", "processing"]))
            .order_by(Document.created_at)
            .limit(50)
        )
    ).all()
    return {
        "by_status": by_status,
        "queue_depth": worker.queue.qsize(),
        "workers": sum(1 for t in worker.tasks if not t.done()),
        "avg_processing_seconds_24h": round(avg_seconds or 0, 1),
        "in_flight": [
            {"label": f"D{seq}", "stage": stage, "status": st, "since": at, "profile": ht}
            for seq, stage, st, at, ht in in_flight
        ],
        "failed": [
            {
                "id": str(d.id),
                "label": d.label,
                "profile": ht,
                "stage": d.stage,
                "error": _sanitize_doc_error(d.error),
                "uploader_role": d.uploader_role,
                "uploaded_at": d.created_at,
                "failed_at": d.updated_at,
            }
            for d, ht in failed
        ],
    }


@router.post("/documents/{doc_id}/retry")
async def retry_document(
    doc_id: uuid.UUID, admin: User = Depends(require_admin), db: AsyncSession = Depends(get_db)
) -> dict[str, Any]:
    doc = await db.get(Document, doc_id)
    if doc is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Document not found")
    if doc.status != "failed":
        raise HTTPException(status.HTTP_409_CONFLICT, "Only failed documents can be retried")
    profile = await db.get(HealthProfile, doc.profile_id)
    doc.status, doc.stage, doc.error = "queued", "Uploading", None
    await db.commit()
    worker.enqueue(doc.id)
    telemetry.event(
        "document_retried",
        f"{admin.name} retried document {doc.label} of {profile.healththread_id if profile else 'a profile'}",
        user_id=admin.id,
    )
    return {"ok": True}


# ───────────────────────────── sharing & emergency ─────────────────────────────


@router.get("/sharing")
async def sharing_metrics(_: User = Depends(require_admin), db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    now = utcnow()
    week = _since(24 * 7)

    async def count(model: Any, *where: Any) -> int:
        return int(await db.scalar(select(func.count()).select_from(model).where(*where)) or 0)

    views = (
        await db.execute(
            select(AuditEvent, HealthProfile.healththread_id)
            .join(HealthProfile, HealthProfile.id == AuditEvent.profile_id)
            .where(AuditEvent.action == "emergency_view")
            .order_by(AuditEvent.created_at.desc())
            .limit(20)
        )
    ).all()
    return {
        "consents_by_status": dict(
            (await db.execute(select(Consent.status, func.count()).group_by(Consent.status))).all()
        ),
        "active": await count(Consent, Consent.status == "active"),
        "expiring_24h": await count(
            Consent, Consent.status == "active", Consent.expires_at <= now + timedelta(hours=24)
        ),
        "created_7d": await count(Consent, Consent.created_at >= week),
        "revoked_7d": await count(Consent, Consent.revoked_at >= week),
        "emergency_cards_enabled": await count(EmergencyCard, EmergencyCard.enabled.is_(True)),
        "emergency_views_24h": await count(
            AuditEvent, AuditEvent.action == "emergency_view", AuditEvent.created_at >= _since(24)
        ),
        "emergency_views_7d": await count(
            AuditEvent, AuditEvent.action == "emergency_view", AuditEvent.created_at >= week
        ),
        "invalid_links_24h": await count(
            SystemEvent, SystemEvent.kind == "invalid_token", SystemEvent.created_at >= _since(24)
        ),
        "recent_emergency_views": [
            {
                "at": ev.created_at,
                "profile": ht,
                "ip": ev.ip,
                "user_agent": str((ev.details or {}).get("user_agent", ""))[:120],
            }
            for ev, ht in views
        ],
    }


# ───────────────────────────── system health ─────────────────────────────


@router.get("/health")
async def system_health(_: User = Depends(require_admin), db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    db_ok = fhir_ok = False
    fhir_version = None
    try:
        await db.execute(text("SELECT 1"))
        db_ok = True
    except Exception:
        pass
    try:
        meta = await get_fhir().metadata()
        fhir_ok = meta.get("resourceType") == "CapabilityStatement"
        fhir_version = meta.get("fhirVersion")
    except Exception:
        pass
    s = get_settings()
    return {
        "started_at": telemetry.STARTED_AT,
        "uptime_seconds": int((utcnow() - telemetry.STARTED_AT).total_seconds()),
        "demo_mode": s.demo_mode,
        "dependencies": {
            "database": {"ok": db_ok},
            "fhir": {"ok": fhir_ok, "version": fhir_version, "url": s.fhir_base_url},
            "ai": {
                "ok": bool(s.gemini_api_key),
                "model": s.gemini_model,
                "fallback_model": s.gemini_fallback_model or None,
            },
            "registry": {"ok": registry.describe()["configured"], **registry.describe()},
        },
        "ingest_worker": {
            "queue_depth": worker.queue.qsize(),
            "workers_alive": sum(1 for t in worker.tasks if not t.done()),
        },
        "jobs": [
            {
                "name": name,
                "runs": j.runs,
                "last_run": j.last_run,
                "ok": j.last_ok,
                "result": j.last_result,
                "error": j.last_error,
                "interval_seconds": j.interval_seconds,
            }
            for name, j in sorted(telemetry.jobs.items())
        ],
        "telemetry_buffer": telemetry.buffered(),
    }


# ───────────────────────────── users ─────────────────────────────


@router.get("/users")
async def users(
    q: str | None = Query(default=None, max_length=100),
    role: Literal["patient", "doctor", "admin", "none"] | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    _: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    profiles = (
        select(func.count()).select_from(HealthProfile).where(HealthProfile.owner_user_id == User.id).scalar_subquery()
    )
    query = select(User, DoctorProfile.verification_status, profiles).outerjoin(
        DoctorProfile, DoctorProfile.user_id == User.id
    )
    if q:
        like = f"%{q.strip()}%"
        query = query.where(or_(User.name.ilike(like), User.email.ilike(like)))
    if role == "none":
        query = query.where(User.role.is_(None))
    elif role:
        query = query.where(User.role == role)
    total = await db.scalar(select(func.count()).select_from(query.subquery()))
    rows = (await db.execute(query.order_by(User.created_at.desc()).limit(limit).offset(offset))).all()
    return {
        "total": total,
        "items": [
            {
                "id": str(u.id),
                "name": u.name,
                "email": u.email,
                "role": u.role,
                "doctor_status": dstatus,
                "profiles": n,
                "created_at": u.created_at,
                "last_login_at": u.last_login_at,
                "sign_in": "demo" if u.google_sub.startswith("demo:") else "google",
            }
            for u, dstatus, n in rows
        ],
    }
