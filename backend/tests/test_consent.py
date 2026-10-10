"""Consent enforcement (spec §10.3), sharing flows, access log and the emergency card."""

import hashlib
import uuid
from datetime import date, timedelta
from pathlib import Path

import pytest
from sqlalchemy import select

from app.db import utcnow
from app.models import AuditEvent, Consent, Notification
from app.services import record as record_service
from app.services.consent import filter_record
from app.services.ingest import pipeline
from app.services.record import Condition, DocumentInfo, Medication, PatientRecord, SourceRef
from tests.conftest import login, make_user
from tests.test_ingest import fixture_result

ROOT = Path(__file__).resolve().parents[2]
ALL_FOUR = ["allergies", "conditions", "labs", "medications"]


@pytest.fixture(autouse=True)
def _isolate(settings, tmp_path, monkeypatch):
    settings.storage_dir = tmp_path / "storage"
    record_service.invalidate()
    monkeypatch.setattr(pipeline.worker, "enqueue", lambda doc_id: None)
    names: dict[str, str] = {}

    async def fake_extract(data, mime, sha256):
        return fixture_result(names[sha256]), "ai"

    monkeypatch.setattr(pipeline, "extract_document", fake_extract)
    return names


@pytest.fixture
async def world(client, db, _isolate):
    owner = await make_user(db, email="priya@x.com", role="patient", name="Priya Rajan")
    doctor = await make_user(db, email="meena@x.com", role="doctor", name="Dr. Meena", doctor_status="verified")
    pending = await make_user(db, email="arjun@x.com", role="doctor", name="Dr. Arjun", doctor_status="pending")
    admin = await make_user(db, email="admin@x.com", role="admin", name="Admin")
    login(client, owner)
    pid = (
        await client.post(
            "/api/profiles",
            json={"display_name": "Rajan Subramanian", "relationship": "parent", "dob": "1962-05-14", "sex": "male"},
        )
    ).json()["id"]
    files = []
    for p in sorted((ROOT / "demo_data" / "rajan").iterdir()):
        data = p.read_bytes()
        _isolate[hashlib.sha256(data).hexdigest()] = p.stem
        files.append(("files", (p.name, data)))
    for r in (await client.post(f"/api/profiles/{pid}/documents", files=files)).json():
        await pipeline.process_document(r["document"]["id"])
    for item in (await client.get(f"/api/profiles/{pid}/review")).json():
        await client.post(f"/api/review/{item['id']}", json={"action": "confirm"})
    return {"owner": owner, "doctor": doctor, "pending": pending, "admin": admin, "pid": pid}


async def share_and_claim(client, w, scopes, hours=168, can_write=False):
    login(client, w["owner"])
    created = (
        await client.post(
            f"/api/profiles/{w['pid']}/shares", json={"scopes": scopes, "duration_hours": hours, "can_write": can_write}
        )
    ).json()
    login(client, w["doctor"])
    claimed = await client.post(f"/api/share/{created['token']}/claim")
    assert claimed.status_code == 200, claimed.text
    return created


CLINICAL = ["timeline", "trends", "medications", "documents", "alerts", "orgs"]


async def test_qr_share_claim_and_scoped_reads(client, db, world):
    created = await share_and_claim(client, world, ["labs"])
    assert created["url"].endswith(created["token"]) and "/share/" in created["url"]
    stored = await db.scalar(select(Consent).where(Consent.profile_id == world["pid"]))
    assert stored.share_token_hash != created["token"]  # only the hash is stored
    pid = world["pid"]

    # Labs only: no medicines, conditions or allergies anywhere.
    assert (await client.get(f"/api/profiles/{pid}/medications")).json()["medications"] == []
    tl = (await client.get(f"/api/profiles/{pid}/timeline")).json()
    assert {i["group"] for i in tl["items"]} <= {"labs", "documents"}
    assert any(i["group"] == "labs" for i in tl["items"])
    trends = (await client.get(f"/api/profiles/{pid}/trends")).json()["analytes"]
    assert any(a["loinc"] == "33914-3" for a in trends)
    assert (await client.get(f"/api/profiles/{pid}/alerts")).json() == []  # every alert needs a non-lab scope
    # Document library is empty without the documents scope...
    assert (await client.get(f"/api/profiles/{pid}/documents")).json() == []
    # ...but a lab report cited by a visible result opens; a prescription does not.
    login(client, world["owner"])
    docs = {d["original_filename"]: d["id"] for d in (await client.get(f"/api/profiles/{pid}/documents")).json()}
    login(client, world["doctor"])
    assert (await client.get(f"/api/documents/{docs['medline_2026-08-05_lab.pdf']}/file")).status_code == 200
    assert (await client.get(f"/api/documents/{docs['anand_2026-02-18_rx.png']}/file")).status_code == 403
    # Profile demographics are always visible; export is owner-only.
    assert (await client.get(f"/api/profiles/{pid}")).json()["display_name"] == "Rajan Subramanian"
    assert (await client.get(f"/api/profiles/{pid}/export")).status_code == 403
    # The patient was notified.
    note = await db.scalar(
        select(Notification).where(Notification.user_id == world["owner"].id, Notification.type == "share_claimed")
    )
    assert note is not None and "Dr. Meena" in note.title


async def test_full_scope_doctor_sees_all_four_alerts(client, world):
    await share_and_claim(client, world, ALL_FOUR)
    alerts = (await client.get(f"/api/profiles/{world['pid']}/alerts")).json()
    assert sorted(a["type"] for a in alerts) == [
        "allergy_conflict",
        "duplicate_therapy",
        "lab_drift",
        "prescribing_cascade",
    ]
    meds = (await client.get(f"/api/profiles/{world['pid']}/medications")).json()["medications"]
    assert len(meds) == 7


async def test_revoked_consent_is_403_on_the_next_request(client, world):
    await share_and_claim(client, world, ALL_FOUR)
    pid = world["pid"]
    assert (await client.get(f"/api/profiles/{pid}/timeline")).status_code == 200
    login(client, world["owner"])
    consent = next(c for c in (await client.get(f"/api/profiles/{pid}/consents")).json() if c["status"] == "active")
    assert (await client.post(f"/api/consents/{consent['id']}/revoke")).status_code == 200
    login(client, world["doctor"])
    for section in CLINICAL:
        assert (await client.get(f"/api/profiles/{pid}/{section}")).status_code == 403, section
    assert (await client.get("/api/doctor/patients")).json() == []


async def test_expired_consent_is_403(client, db, world):
    await share_and_claim(client, world, ALL_FOUR, hours=24)
    c = await db.scalar(select(Consent).where(Consent.profile_id == world["pid"], Consent.status == "active"))
    c.expires_at = utcnow() - timedelta(minutes=1)
    await db.commit()
    for section in CLINICAL:
        assert (await client.get(f"/api/profiles/{world['pid']}/{section}")).status_code == 403, section
    await db.refresh(c)
    assert c.status == "expired"


async def test_unverified_doctor_and_admin_are_403(client, world):
    login(client, world["owner"])
    token = (await client.post(f"/api/profiles/{world['pid']}/shares", json={"scopes": ALL_FOUR})).json()["token"]
    login(client, world["pending"])
    preview = (await client.get(f"/api/share/{token}")).json()
    assert "awaiting verification" in preview["problem"]
    assert (await client.post(f"/api/share/{token}/claim")).status_code == 403
    for who in ("pending", "admin"):
        login(client, world[who])
        for section in [*CLINICAL, "export", "review"]:
            assert (await client.get(f"/api/profiles/{world['pid']}/{section}")).status_code == 403, (who, section)
        assert (
            await client.post(f"/api/profiles/{world['pid']}/prescriptions/check", json={"drug": "Novamox"})
        ).status_code == 403


async def test_doctor_without_consent_and_stale_qr(client, db, world):
    login(client, world["doctor"])
    assert (await client.get(f"/api/profiles/{world['pid']}/timeline")).status_code == 403
    login(client, world["owner"])
    token = (await client.post(f"/api/profiles/{world['pid']}/shares", json={"scopes": ALL_FOUR})).json()["token"]
    c = await db.scalar(select(Consent).where(Consent.status == "pending_claim"))
    c.claim_deadline = utcnow() - timedelta(seconds=1)
    await db.commit()
    login(client, world["doctor"])
    assert (await client.post(f"/api/share/{token}/claim")).status_code == 410
    assert (await client.post("/api/share/not-a-real-token/claim")).status_code == 404


async def test_access_request_approve_narrow_and_deny(client, db, world):
    login(client, world["owner"])
    ht_id = (await client.get(f"/api/profiles/{world['pid']}")).json()["healththread_id"]
    login(client, world["doctor"])
    assert (await client.post("/api/doctor/requests", json={"identifier": "HT-XXXX-XXXX"})).status_code == 404
    assert (await client.post("/api/doctor/requests", json={"identifier": "nobody@x.com"})).status_code == 404
    req = await client.post(
        "/api/doctor/requests", json={"identifier": ht_id.lower(), "scopes": ALL_FOUR, "duration_hours": 720}
    )
    assert req.status_code == 200
    assert (await client.post("/api/doctor/requests", json={"identifier": ht_id})).status_code == 409
    assert (await client.get(f"/api/profiles/{world['pid']}/timeline")).status_code == 403  # not approved yet

    login(client, world["owner"])
    pending = next(
        c for c in (await client.get(f"/api/profiles/{world['pid']}/consents")).json() if c["status"] == "requested"
    )
    assert pending["doctor"]["verified"] is True
    widen = await client.post(f"/api/consents/{pending['id']}/approve", json={"scopes": [*ALL_FOUR, "mental_health"]})
    assert widen.status_code == 422
    ok = await client.post(f"/api/consents/{pending['id']}/approve", json={"scopes": ["labs"], "duration_hours": 24})
    assert ok.json()["status"] == "active" and ok.json()["scopes"] == ["labs"]

    login(client, world["doctor"])
    assert (await client.get(f"/api/profiles/{world['pid']}/medications")).json()["medications"] == []
    assert (await client.get(f"/api/profiles/{world['pid']}/trends")).status_code == 200


async def test_email_request_and_deny(client, world):
    login(client, world["doctor"])
    r = await client.post("/api/doctor/requests", json={"identifier": "PRIYA@x.com"})
    assert r.status_code == 200
    login(client, world["owner"])
    req = next(
        c for c in (await client.get(f"/api/profiles/{world['pid']}/consents")).json() if c["status"] == "requested"
    )
    assert (await client.post(f"/api/consents/{req['id']}/deny")).json()["status"] == "denied"
    login(client, world["doctor"])
    assert (await client.get("/api/doctor/requests")).json()[0]["status"] == "denied"


async def test_access_log_records_doctor_views(client, db, world):
    await share_and_claim(client, world, ALL_FOUR)
    await client.get(f"/api/profiles/{world['pid']}/trends")
    await client.get(f"/api/profiles/{world['pid']}/medications")
    login(client, world["owner"])
    log = (await client.get(f"/api/profiles/{world['pid']}/audit")).json()
    views = [e for e in log if e["action"] == "view"]
    assert {e["details"]["section"] for e in views} >= {"trends", "medications"}
    assert all("Dr. Meena" in e["actor"] for e in views)
    login(client, world["doctor"])
    assert (await client.get(f"/api/profiles/{world['pid']}/audit")).status_code == 403


def test_mental_health_items_and_their_documents_are_hidden_without_the_scope():
    src = SourceRef("doc-psych", "D3", 1, "Dx: Depression", "Mind Clinic", "2025-01-01", "psych.pdf")
    rec = PatientRecord(
        profile_id=uuid.uuid4(),
        version=1,
        patient_ref="Patient/1",
        display_name="X",
        dob=date(1970, 1, 1),
        sex="female",
        blood_group="O+",
        conditions=[
            Condition("Condition/1", "Depressive episode", "F32.9", "active", None, None, "Mind Clinic", [src]),
            Condition("Condition/2", "Hypothyroidism", "E03.9", "active", None, None, "Greenfield", []),
        ],
        medications=[
            Medication(
                "MedicationRequest/1",
                "sertraline",
                "Sertraline 50 mg",
                "Daxid",
                {"ssri", "psychiatric"},
                "50 mg",
                50.0,
                "1-0-0",
                "1-0-0",
                1,
                False,
                None,
                date(2025, 1, 1),
                None,
                "active",
                "Mind Clinic",
                None,
                None,
                [src],
            )
        ],
        documents=[
            DocumentInfo(
                "doc-psych",
                "D3",
                3,
                None,
                "psych.pdf",
                "application/pdf",
                1,
                "opd_note",
                "Mind Clinic",
                "2025-01-01",
                "done",
                "owner",
                "2025-01-01T00:00:00",
            )
        ],
    )
    scoped = filter_record(rec, frozenset(["conditions", "medications", "documents"]))
    assert [c.text for c in scoped.conditions] == ["Hypothyroidism"] and scoped.medications == []
    assert scoped.documents == []  # the psych note can't leak through the library or citations
    full = filter_record(rec, frozenset(["conditions", "medications", "documents", "mental_health"]))
    assert len(full.conditions) == 2 and len(full.medications) == 1 and len(full.documents) == 1


async def test_emergency_card_flow(client, db, world):
    login(client, world["owner"])
    pid = world["pid"]
    assert (await client.get(f"/api/profiles/{pid}/emergency")).json()["enabled"] is False
    card = (await client.post(f"/api/profiles/{pid}/emergency/enable")).json()
    token = card["token"]
    client.cookies.clear()  # anonymous responder
    public = await client.get(f"/api/emergency/{token}")
    assert public.status_code == 200
    data = public.json()
    assert set(data) == {
        "name",
        "age",
        "sex",
        "blood_group",
        "allergies",
        "medications",
        "conditions",
        "emergency_contact",
        "healththread_id",
        "last_updated",
    }
    assert [a["substance"] for a in data["allergies"]] == ["Penicillin"]
    assert {m["name"].split(" ")[0] for m in data["medications"]} == {"Metformin", "Ramipril", "Aspirin", "Paracetamol"}
    assert "labs" not in data and "documents" not in data
    ev = await db.scalar(select(AuditEvent).where(AuditEvent.action == "emergency_view"))
    assert ev is not None and ev.actor_user_id is None
    note = await db.scalar(select(Notification).where(Notification.type == "emergency_view"))
    assert note is not None and note.title.startswith("Emergency access to Rajan's card at")

    login(client, world["owner"])
    pdf = await client.post(f"/api/profiles/{pid}/emergency/wallet.pdf", json={"token": token})
    assert pdf.status_code == 200 and pdf.content.startswith(b"%PDF")
    png = await client.post(f"/api/profiles/{pid}/emergency/lockscreen.png", json={"token": token})
    assert png.status_code == 200 and png.content.startswith(b"\x89PNG")
    new = (await client.post(f"/api/profiles/{pid}/emergency/enable")).json()["token"]
    client.cookies.clear()
    assert (await client.get(f"/api/emergency/{token}")).status_code == 404  # old QR is dead
    assert (await client.get(f"/api/emergency/{new}")).status_code == 200
    login(client, world["owner"])
    await client.post(f"/api/profiles/{pid}/emergency/disable")
    client.cookies.clear()
    assert (await client.get(f"/api/emergency/{new}")).status_code == 404
    login(client, world["doctor"])
    assert (await client.post(f"/api/profiles/{pid}/emergency/enable")).status_code == 403


async def test_new_share_replaces_previous_consent_for_same_doctor(client, db, world):
    await share_and_claim(client, world, ["labs"])
    await share_and_claim(client, world, ALL_FOUR)
    active = (
        await db.scalars(select(Consent).where(Consent.profile_id == world["pid"], Consent.status == "active"))
    ).all()
    assert len(active) == 1 and sorted(active[0].scopes) == ALL_FOUR
    patients = (await client.get("/api/doctor/patients")).json()
    assert len(patients) == 1
