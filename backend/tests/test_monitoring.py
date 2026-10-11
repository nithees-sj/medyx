"""Admin monitoring: telemetry capture, the metric endpoints, and the privacy boundary."""

import json
import time
from datetime import date

import pytest
from sqlalchemy import select

from app.ai import client as ai_client
from app.models import Document, RequestLog, SystemEvent
from app.services import telemetry
from app.services.audit import log_event
from app.services.profiles import create_profile
from tests.conftest import login, make_user

ADMIN_ENDPOINTS = ["overview", "activity", "requests", "ai", "pipeline", "sharing", "health", "users"]


async def _profile(db, owner, name="Rajan Subramanian"):
    return await create_profile(
        db, owner_user_id=owner.id, display_name=name, relationship="parent", dob=date(1962, 5, 14),
        sex="male", blood_group="B+", emergency_contact_name=None, emergency_contact_phone=None,
    )  # fmt: skip


@pytest.mark.parametrize("who", ["patient", "doctor"])
async def test_monitoring_is_admin_only(client, db, who):
    user = await make_user(db, email=f"{who}@x.com", role=who, doctor_status="verified" if who == "doctor" else None)
    login(client, user)
    for ep in ADMIN_ENDPOINTS:
        assert (await client.get(f"/api/admin/{ep}")).status_code == 403, ep


async def test_requests_are_recorded_with_route_templates_and_denials(client, db):
    owner = await make_user(db, email="priya@x.com", role="patient")
    stranger = await make_user(db, email="s@x.com", role="doctor", doctor_status="verified")
    profile = await _profile(db, owner)
    await db.commit()
    login(client, owner)
    assert (await client.get(f"/api/profiles/{profile.id}/timeline")).status_code == 200
    login(client, stranger)
    for _ in range(3):  # repeated denials collapse into one event
        assert (await client.get(f"/api/profiles/{profile.id}/timeline")).status_code == 403
    assert (await client.get("/api/emergency/not-a-real-token-123456789")).status_code == 404
    await telemetry.flush()

    rows = (await db.scalars(select(RequestLog).order_by(RequestLog.id))).all()
    timeline = [r for r in rows if r.route == "/api/profiles/{profile_id}/timeline"]
    assert [r.status for r in timeline] == [200, 403, 403, 403]
    assert timeline[0].user_id == owner.id and timeline[0].role == "patient"
    assert all(str(profile.id) not in r.route for r in rows)
    kinds = [e.kind for e in (await db.scalars(select(SystemEvent))).all()]
    assert kinds.count("access_denied") == 1 and kinds.count("invalid_token") == 1

    admin = await make_user(db, email="admin@x.com", role="admin")
    login(client, admin)
    m = (await client.get("/api/admin/requests")).json()
    route = next(r for r in m["routes"] if r["route"] == "/api/profiles/{profile_id}/timeline")
    assert route["requests"] == 4 and route["client_errors"] == 3
    assert m["totals"]["requests"] >= 5 and m["series"]


async def test_ai_calls_are_recorded_without_content(client, db):
    ai_client._log_usage("extract", time.monotonic() - 1.2, None, True, "gemini-test")
    ai_client._log_usage("chat", time.monotonic(), None, False, "gemini-test", "HTTP 429")
    ai_client._log_usage("chat", time.monotonic(), None, True, "gemini-lite")
    await telemetry.flush()
    admin = await make_user(db, email="admin@x.com", role="admin")
    login(client, admin)
    m = (await client.get("/api/admin/ai")).json()
    assert m["totals"]["calls"] == 3 and m["totals"]["failures"] == 1 and m["totals"]["rate_limited"] == 1
    chat = next(p for p in m["by_purpose"] if p["key"] == "chat")
    assert chat["calls"] == 2 and chat["rate_limited"] == 1
    assert {r["model"] for r in m["recent"]} == {"gemini-test", "gemini-lite"}
    assert set(m["recent"][0]) == {"at", "purpose", "model", "ok", "ms", "input_tokens", "output_tokens", "error"}


async def test_activity_feed_hides_clinical_details(client, db):
    owner = await make_user(db, email="priya@x.com", role="patient", name="Priya Rajan")
    doctor = await make_user(db, email="d@x.com", role="doctor", name="Dr. Meena", doctor_status="verified")
    profile = await _profile(db, owner)
    for action, details, scopes in [
        ("upload", {"document": "D3", "filename": "hiv_test_result.pdf"}, ["documents"]),
        (
            "prescribe",
            {
                "medicine": "Novamox 500",
                "override_reason": "Allergy was mild rash in 1998",
                "alerts": ["Critical: Penicillin allergy vs amoxicillin"],
            },
            ["medications"],
        ),  # fmt: skip
        ("chat", {"question_chars": 64}, ["labs"]),
        ("view", {"section": "panel insights", "question": "Which of my patients have HIV?"}, []),
        (
            "alert_review",
            {
                "alert": "Penicillin allergy vs amoxicillin",
                "status": "reviewed_intentional",
                "note": "patient tolerated it",
            },
            ["allergies"],
        ),  # fmt: skip
        ("consent_change", {"event": "access_requested", "purpose": "Suspected depression follow-up"}, ["labs"]),
        ("emergency_view", {"user_agent": "Mozilla/5.0"}, []),
    ]:
        await log_event(
            db, profile_id=profile.id, actor_user_id=doctor.id if action != "upload" else owner.id,
            actor_label="Dr. Meena (Nephrology)" if action != "upload" else "Priya Rajan (account owner)",
            action=action, scopes=scopes, details=details, ip="10.0.0.1",
        )  # fmt: skip
    await db.commit()
    telemetry.event("login", "Priya Rajan signed in (demo account)", user_id=owner.id)
    await telemetry.flush()

    admin = await make_user(db, email="admin@x.com", role="admin")
    login(client, admin)
    feed = (await client.get("/api/admin/activity?limit=50")).json()
    blob = json.dumps(feed)
    for leaked in ("Rajan Subramanian", "hiv", "HIV", "Novamox", "Penicillin", "amoxicillin", "mild rash",
                   "tolerated", "depression", "question\""):  # fmt: skip
        assert leaked not in blob, leaked
    record = [i for i in feed["items"] if i["source"] == "record"]
    assert {i["target"] for i in record} == {profile.healththread_id}
    summaries = {i["kind"]: i["summary"] for i in record}
    assert summaries["upload"] == "uploaded document D3"
    assert summaries["prescribe"] == "issued a prescription — overriding a critical safety alert"
    assert summaries["view"] == "viewed panel insights"
    assert summaries["alert_review"] == "marked a safety alert as reviewed intentional"
    assert summaries["consent_change"].startswith("requested access")
    assert next(i for i in record if i["kind"] == "emergency_view")["severity"] == "warning"
    assert any(i["source"] == "system" and i["category"] == "auth" for i in feed["items"])
    # Filters and paging.
    sec = (await client.get("/api/admin/activity?category=emergency")).json()["items"]
    assert [i["kind"] for i in sec] == ["emergency_view"]
    page = (await client.get("/api/admin/activity?limit=3")).json()
    older = (await client.get(f"/api/admin/activity?limit=50&before={page['next_before']}")).json()["items"]
    assert len(page["items"]) == 3 and len(older) == len(feed["items"]) - 3


async def test_pipeline_errors_are_sanitized_and_retryable(client, db):
    owner = await make_user(db, email="priya@x.com", role="patient")
    profile = await _profile(db, owner)
    doc = Document(
        profile_id=profile.id, seq=4, uploaded_by_user_id=owner.id, uploader_role="owner",
        original_filename="rajan_hba1c_report.pdf", mime="application/pdf", storage_path="/nowhere", sha256="0",
        status="failed", stage="Failed", error="FHIR 422: Observation.valueQuantity 7.8 % HbA1c rejected",
    )  # fmt: skip
    db.add(doc)
    await db.commit()
    admin = await make_user(db, email="admin@x.com", role="admin")
    login(client, admin)
    p = (await client.get("/api/admin/pipeline")).json()
    assert p["by_status"] == {"failed": 1}
    failed = p["failed"][0]
    assert failed["label"] == "D4" and failed["profile"] == profile.healththread_id
    assert failed["error"] == "The FHIR server rejected the write (HTTP 422)"
    assert "HbA1c" not in json.dumps(p) and "rajan" not in json.dumps(p)
    assert (await client.post(f"/api/admin/documents/{doc.id}/retry")).json() == {"ok": True}
    await db.refresh(doc)
    assert doc.status == "queued"
    assert (await client.post(f"/api/admin/documents/{doc.id}/retry")).status_code == 409


async def test_overview_health_users_and_sharing(client, db, settings):
    settings.demo_mode = True
    admin = await make_user(db, email="admin@x.com", role="admin", name="Admin")
    await make_user(db, email="pending@x.com", role="doctor", name="Dr. Pending", doctor_status="pending")
    owner = await make_user(db, email="priya@x.com", role="patient", name="Priya Rajan")
    await _profile(db, owner)
    await db.commit()
    assert (await client.post("/api/auth/demo", json={"persona": "priya"})).status_code == 200
    await telemetry.flush()
    login(client, admin)

    ov = (await client.get("/api/admin/overview")).json()
    assert ov["kpis"]["users_by_role"]["doctor"] == 1 and ov["kpis"]["doctors"]["pending"] == 1
    assert ov["last_24h"]["sign_ins"] == 1
    assert len(ov["daily"]) == 14 and ov["daily"][-1]["sign_ins"] == 1
    assert any(a["kind"] == "doctors_pending" and a["count"] == 1 for a in ov["attention"])

    health = (await client.get("/api/admin/health")).json()
    assert health["dependencies"]["database"]["ok"] is True
    assert health["dependencies"]["registry"]["configured"] is False

    found = (await client.get("/api/admin/users?q=priya")).json()
    assert {u["email"] for u in found["items"]} >= {"priya@x.com"}
    mine = next(u for u in found["items"] if u["email"] == "priya@x.com")
    assert mine["profiles"] == 1 and mine["sign_in"] == "google"
    assert (await client.get("/api/admin/users?role=doctor")).json()["items"][0]["doctor_status"] == "pending"

    sharing = (await client.get("/api/admin/sharing")).json()
    assert sharing["active"] == 0 and sharing["recent_emergency_views"] == []
