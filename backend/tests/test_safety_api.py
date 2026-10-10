"""Acceptance: Rajan → exactly the 4 expected alerts, Lakshmi → 0, idempotent re-runs (real saved extractions)."""

import hashlib
from pathlib import Path

import pytest
from sqlalchemy import select

from app.models import Alert
from app.services import record as record_service
from app.services.ingest import pipeline
from tests.conftest import login, make_user
from tests.test_ingest import fixture_result

ROOT = Path(__file__).resolve().parents[2]


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


async def ingest(client, db, names, folder: str, person: dict) -> str:
    resp = await client.post("/api/profiles", json={"relationship": "parent", **person})
    pid = resp.json()["id"]
    files = []
    for p in sorted((ROOT / "demo_data" / folder).iterdir()):
        data = p.read_bytes()
        names[hashlib.sha256(data).hexdigest()] = p.stem
        files.append(("files", (p.name, data)))
    for r in (await client.post(f"/api/profiles/{pid}/documents", files=files)).json():
        await pipeline.process_document(r["document"]["id"])
    return pid


async def confirm_all(client, pid):
    for item in (await client.get(f"/api/profiles/{pid}/review")).json():
        assert (await client.post(f"/api/review/{item['id']}", json={"action": "confirm"})).status_code == 200


RAJAN = {"display_name": "Rajan Subramanian", "dob": "1962-05-14", "sex": "male", "blood_group": "B+"}
LAKSHMI = {"display_name": "Lakshmi Iyer", "dob": "1968-03-09", "sex": "female"}


async def test_rajan_gets_exactly_the_four_expected_alerts(client, db, _isolate):
    owner = await make_user(db, email="priya@x.com", role="patient", name="Priya Rajan")
    login(client, owner)
    pid = await ingest(client, db, _isolate, "rajan", RAJAN)
    before = (await client.get(f"/api/profiles/{pid}/alerts")).json()
    assert sorted(a["type"] for a in before) == ["duplicate_therapy", "lab_drift", "prescribing_cascade"]

    await confirm_all(client, pid)  # the penicillin allergy waits in review (year-only date)
    alerts = (await client.get(f"/api/profiles/{pid}/alerts")).json()
    by_type = {a["type"]: a for a in alerts}
    assert sorted(by_type) == ["allergy_conflict", "duplicate_therapy", "lab_drift", "prescribing_cascade"]
    assert len(alerts) == 4
    assert alerts[0]["type"] == "allergy_conflict" and alerts[0]["severity"] == "critical"

    dup = by_type["duplicate_therapy"]
    assert dup["severity"] == "warning" and "metformin" in dup["title"]
    assert {e["label"].split("(")[-1].rstrip(")") for e in dup["evidence"]} == {"Glycomet", "Glucophage"}
    assert {e["org"] for e in dup["evidence"]} == {"Sunrise Diabetes & Multispeciality Hospital", "Anand Family Clinic"}

    allergy = by_type["allergy_conflict"]
    assert "Penicillin" in allergy["title"] and "Novamox" in allergy["title"]

    casc = by_type["prescribing_cascade"]
    assert casc["rule_id"] == "prescribing_cascade:acei_cough"
    assert [e["date"] for e in casc["evidence"]] == ["2025-01-20", "2025-04-02"]

    drift = by_type["lab_drift"]
    assert drift["severity"] == "warning" and "metformin" in drift["title"]
    egfr = drift["details"]["series"]["33914-3"]
    assert [p["value"] for p in egfr["fitted"]] and egfr["projected_cross_date"].startswith("2026-")
    egfr_labels = [e for e in drift["evidence"] if e["label"].startswith("eGFR")]
    assert len(egfr_labels) == 4 and len({e["org"] for e in egfr_labels}) == 4
    assert all(
        a["patient_text"].endswith("Please discuss this with a doctor before changing any medicine.") for a in alerts
    )
    assert all(e["document_id"] and e["page"] for a in alerts for e in a["evidence"])

    # Re-running creates no duplicates.
    for _ in range(2):
        r = await client.post(f"/api/profiles/{pid}/alerts/rerun")
        assert r.json()["created"] == 0
    rows = (await db.scalars(select(Alert).where(Alert.profile_id == pid))).all()
    current = [a for a in rows if not (a.details or {}).get("superseded_by")]
    assert len(current) == 4 and all(a.status == "active" for a in current)
    assert len((await client.get(f"/api/profiles/{pid}/alerts?include=all")).json()) == 4

    # The trends endpoint carries the drift projection.
    trends = (await client.get(f"/api/profiles/{pid}/trends")).json()["analytes"]
    assert next(a for a in trends if a["loinc"] == "33914-3")["drift"]["projected_cross_date"]


async def test_lakshmi_control_patient_has_zero_alerts(client, db, _isolate):
    owner = await make_user(db, email="lakshmi@x.com", role="patient", name="Lakshmi Iyer")
    login(client, owner)
    pid = await ingest(client, db, _isolate, "lakshmi", {**LAKSHMI, "relationship": "self"})
    await confirm_all(client, pid)
    await client.post(f"/api/profiles/{pid}/alerts/rerun")
    assert (await client.get(f"/api/profiles/{pid}/alerts?include=all")).json() == []
    tsh = next(
        a for a in (await client.get(f"/api/profiles/{pid}/trends")).json()["analytes"] if a["loinc"] == "3016-3"
    )
    assert [p["value"] for p in tsh["points"]] == [2.1, 2.4, 1.9]


async def test_reviewed_intentional_stays_suppressed_and_prescribe_check(client, db, _isolate):
    owner = await make_user(db, email="priya@x.com", role="patient", name="Priya Rajan")
    login(client, owner)
    pid = await ingest(client, db, _isolate, "rajan", RAJAN)
    await confirm_all(client, pid)

    from datetime import timedelta

    from app.db import utcnow
    from app.models import Consent

    doctor = await make_user(db, email="meena@x.com", role="doctor", name="Dr. Meena", doctor_status="verified")
    db.add(
        Consent(
            profile_id=pid,
            granted_by_user_id=owner.id,
            doctor_user_id=doctor.id,
            scopes=["conditions", "medications", "allergies", "labs"],
            can_write=True,
            status="active",
            duration_hours=168,
            expires_at=utcnow() + timedelta(days=7),
        )
    )
    await db.commit()
    login(client, doctor)
    alerts = (await client.get(f"/api/profiles/{pid}/alerts")).json()
    assert len(alerts) == 4  # all evidence inside the doctor's scopes
    dup = next(a for a in alerts if a["type"] == "duplicate_therapy")
    bad = await client.post(f"/api/alerts/{dup['id']}/review", json={"status": "reviewed_intentional"})
    assert bad.status_code == 422
    ok = await client.post(
        f"/api/alerts/{dup['id']}/review",
        json={"status": "reviewed_intentional", "note": "Glucophage replaces Glycomet"},
    )
    assert ok.json()["status"] == "reviewed_intentional"
    await client.post(f"/api/profiles/{pid}/alerts/rerun")
    active = (await client.get(f"/api/profiles/{pid}/alerts")).json()
    assert len(active) == 3 and all(a["type"] != "duplicate_therapy" for a in active)

    check = (await client.post(f"/api/profiles/{pid}/prescriptions/check", json={"drug": "Novamox 500"})).json()
    assert check["draft"]["generic"] == "amoxicillin"
    assert [a["type"] for a in check["alerts"]] == ["allergy_conflict"]
    assert check["alerts"][0]["severity"] == "critical"
    safe = (await client.post(f"/api/profiles/{pid}/prescriptions/check", json={"drug": "Azithral 500"})).json()
    assert safe["alerts"] == []

    # The patient can't review alerts (doctor decision support only).
    login(client, owner)
    r = await client.post(f"/api/alerts/{dup['id']}/review", json={"status": "resolved"})
    assert r.status_code == 403
