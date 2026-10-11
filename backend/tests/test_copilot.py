"""Copilot + doctor actions. The AI boundary is stubbed; everything else is real (fake FHIR)."""

import json
from datetime import timedelta
from types import SimpleNamespace

import pytest
from google.genai import types
from sqlalchemy import select

from app.db import utcnow
from app.models import AuditEvent, ChatMessage, Consent
from app.services.copilot import insights
from app.services.copilot.summary import LabLine, Line, Summary
from tests.conftest import login, make_user
from tests.test_consent import (  # noqa: F401  (fixture)
    ALL_FOUR,
    _isolate,  # noqa: F401  (fixture)
    world,
)


async def grant(db, w, scopes, can_write=False, doctor_key="doctor"):
    db.add(
        Consent(
            profile_id=w["pid"],
            granted_by_user_id=w["owner"].id,
            doctor_user_id=w[doctor_key].id,
            scopes=scopes,
            can_write=can_write,
            status="active",
            duration_hours=168,
            expires_at=utcnow() + timedelta(days=7),
        )
    )
    await db.commit()


def sse_events(text: str) -> list[dict]:
    return [json.loads(line[6:]) for line in text.splitlines() if line.startswith("data: ")]


async def test_chat_context_is_scoped_and_citations_checked(client, db, world, monkeypatch):  # noqa: F811
    await grant(db, world, ["labs"])
    seen = {}

    async def fake_stream(*, purpose, system, contents, **kw):
        seen["system"] = system
        keys = [ln.split("]")[0][1:] for ln in system.splitlines() if ln.startswith("[Observation/")]
        yield f"eGFR fell to 47 [{keys[-1]}]. "
        yield "Also see [MedicationRequest/999]."

    monkeypatch.setattr("app.services.copilot.chat.ai.stream_text", fake_stream)
    login(client, world["doctor"])
    resp = await client.post(f"/api/profiles/{world['pid']}/chat", json={"message": "eGFR trend?"})
    assert resp.status_code == 200 and resp.headers["content-type"].startswith("text/event-stream")
    events = sse_events(resp.text)
    assert [e["type"] for e in events][-1] == "done"
    done = events[-1]
    assert [c for c in done["citations"] if not c.get("unknown")][0]["key"].startswith("Observation/")
    assert any(c.get("unknown") and c["key"] == "MedicationRequest/999" for c in done["citations"])
    # Out-of-scope resources never reach the model.
    sysprompt = seen["system"]
    assert "[Observation/" in sysprompt
    for forbidden in (
        "[MedicationRequest/",
        "[AllergyIntolerance/",
        "[Condition/",
        "Penicillin",
        "Glycomet",
        "Novamox",
    ):
        assert forbidden not in sysprompt, forbidden
    msgs = (await db.scalars(select(ChatMessage).order_by(ChatMessage.created_at))).all()
    assert [m.role for m in msgs] == ["user", "assistant"]
    assert await db.scalar(select(AuditEvent).where(AuditEvent.action == "chat"))
    # The patient can't use the doctor copilot; strangers can't either.
    login(client, world["owner"])
    assert (await client.post(f"/api/profiles/{world['pid']}/chat", json={"message": "hi"})).status_code == 403
    login(client, world["pending"])
    assert (await client.post(f"/api/profiles/{world['pid']}/chat", json={"message": "hi"})).status_code == 403


async def test_full_scope_digest_has_everything(client, db, world, monkeypatch):  # noqa: F811
    await grant(db, world, ALL_FOUR)
    seen = {}

    async def fake_stream(*, purpose, system, contents, **kw):
        seen["system"] = system
        yield "ok"

    monkeypatch.setattr("app.services.copilot.chat.ai.stream_text", fake_stream)
    login(client, world["doctor"])
    events = sse_events((await client.post(f"/api/profiles/{world['pid']}/chat", json={"message": "x"})).text)
    assert events[-1]["uncited"] is True
    s = seen["system"]
    for expected in (
        "Penicillin",
        "Glycomet",
        "Glucophage",
        "[Observation/",
        "ACTIVE SAFETY ALERTS",
        "written as 133 µmol/L",
    ):
        assert expected in s, expected


async def test_summary_cleans_citations_and_caches(client, db, world, monkeypatch):  # noqa: F811
    await grant(db, world, ALL_FOUR)
    calls = {"n": 0}

    async def fake_structured(*, purpose, system, contents, schema, **kw):
        calls["n"] += 1
        key = next(ln.split("]")[0][1:] for ln in system.splitlines() if "eGFR 47" in ln)
        return Summary(
            key_problems=[Line(text="CKD progression", citations=[key, "Observation/doesnotexist"])],
            current_medications=[Line(text="Metformin twice", citations=[])],
            relevant_labs=[LabLine(text="eGFR 72 → 47", citations=[f"[{key}]"], trend="down")],
            active_alerts=[],
            open_questions=[],
        )

    monkeypatch.setattr("app.services.copilot.summary.ai.generate_structured", fake_structured)
    login(client, world["doctor"])
    first = (await client.get(f"/api/profiles/{world['pid']}/summary?specialty=Nephrology")).json()
    assert first["cached"] is False
    kp = first["sections"]["key_problems"][0]
    assert len(kp["citations"]) == 1 and kp["citations"][0]["doc_label"]
    assert first["sections"]["current_medications"][0]["uncited"] is True
    assert first["sections"]["relevant_labs"][0]["trend"] == "down"
    second = (await client.get(f"/api/profiles/{world['pid']}/summary?specialty=Nephrology")).json()
    assert second["cached"] is True and calls["n"] == 1


async def test_insights_tools_only_cover_consented_patients(client, db, world, monkeypatch):  # noqa: F811
    await grant(db, world, ALL_FOUR)
    doctor = world["doctor"]
    await db.refresh(doctor, ["doctor_profile"])
    panel = await insights.load_panel(db, doctor)
    tools = insights.Tools(panel, {})
    res = tools.list_patients_with_lab_trend("eGFR", "down")
    assert [p["name"] for p in res["patients"]] == ["Rajan Subramanian"]
    assert tools.rows[0]["sparkline"][0]["value"] == 72 and tools.rows[0]["slope_per_year"] < -9
    assert tools.list_patients_with_lab_trend("eGFR", "up")["patients"] == []
    assert [p["name"] for p in tools.list_patients_on_drug("metformin")["patients"]] == ["Rajan Subramanian"]
    assert tools.list_patients_on_drug("ace_inhibitor")["patients"]
    assert "error" in tools.get_latest_lab("Unobtainium")

    # End to end with a stubbed model: one tool call, then a final answer.
    turn = {"n": 0}

    async def fake_tools(*, purpose, system, contents, tools, **kw):
        turn["n"] += 1
        if turn["n"] == 1:
            call = types.FunctionCall(
                name="list_patients_with_lab_trend", args={"loinc": "33914-3", "direction": "down"}
            )
            return SimpleNamespace(
                function_calls=[call],
                candidates=[
                    SimpleNamespace(content=types.Content(role="model", parts=[types.Part(function_call=call)]))
                ],
                text=None,
            )
        tool_reply = contents[-1].parts[0].function_response.response["result"]
        names = ", ".join(p["name"] for p in tool_reply["patients"])
        return SimpleNamespace(function_calls=[], candidates=[], text=f"Declining eGFR: {names}.")

    monkeypatch.setattr("app.services.copilot.insights.ai.generate_with_tools", fake_tools)
    login(client, doctor)
    out = (
        await client.post(
            "/api/doctor/insights", json={"question": "Which of my patients have declining kidney function?"}
        )
    ).json()
    assert out["answer"] == "Declining eGFR: Rajan Subramanian."
    assert [r["name"] for r in out["table"]["rows"]] == ["Rajan Subramanian"]
    assert out["panel_size"] == 1
    login(client, world["pending"])
    assert (await client.post("/api/doctor/insights", json={"question": "anything?"})).status_code == 403


async def test_prescribe_requires_override_for_critical_alerts(client, db, world):  # noqa: F811
    await grant(db, world, ALL_FOUR, can_write=True)
    login(client, world["doctor"])
    pid = world["pid"]
    check = (await client.post(f"/api/profiles/{pid}/prescriptions/check", json={"drug": "Novamox 500"})).json()
    assert [a["type"] for a in check["alerts"]] == ["allergy_conflict"] and not check["alerts"][0]["redacted"]
    refused = await client.post(
        f"/api/profiles/{pid}/prescriptions", json={"drug": "Novamox 500", "frequency": "1-1-1", "duration_days": 5}
    )
    assert refused.status_code == 409
    ok = await client.post(
        f"/api/profiles/{pid}/prescriptions",
        json={
            "drug": "Azithral",
            "strength": "500 mg",
            "frequency": "1-0-0",
            "duration_days": 3,
            "instructions": "after food",
        },
    )
    assert ok.status_code == 200, ok.text
    body = ok.json()
    assert body["alerts"] == [] and body["pdf_url"].endswith(".pdf")
    pdf = await client.get(body["pdf_url"])
    assert pdf.status_code == 200 and pdf.content.startswith(b"%PDF")
    meds = (await client.get(f"/api/profiles/{pid}/medications")).json()["medications"]
    azi = next(m for m in meds if m["generic"] == "azithromycin")
    assert azi["requester"] == "Dr. Meena" and azi["status"] == "active"
    override = await client.post(
        f"/api/profiles/{pid}/prescriptions",
        json={
            "drug": "Novamox 500",
            "frequency": "1-1-1",
            "duration_days": 5,
            "override_reason": "Allergy disproven by skin test",
        },
    )
    assert override.status_code == 200
    ev = (await db.scalars(select(AuditEvent).where(AuditEvent.action == "prescribe"))).all()
    assert any((e.details or {}).get("override_reason") == "Allergy disproven by skin test" for e in ev)


async def test_prescribe_needs_can_write_and_redacts_hidden_conflicts(client, db, world):  # noqa: F811
    await grant(db, world, ["medications"], can_write=False)
    login(client, world["doctor"])
    pid = world["pid"]
    r = await client.post(f"/api/profiles/{pid}/prescriptions", json={"drug": "Azithral 500"})
    assert r.status_code == 403
    check = (await client.post(f"/api/profiles/{pid}/prescriptions/check", json={"drug": "Novamox 500"})).json()
    assert check["alerts"][0]["redacted"] is True and check["alerts"][0]["severity"] == "critical"
    assert "Penicillin" not in json.dumps(check)


async def test_notes_and_patient_list(client, db, world, fhir):  # noqa: F811
    await grant(db, world, ALL_FOUR, can_write=True)
    login(client, world["doctor"])
    pid = world["pid"]
    note = await client.post(f"/api/profiles/{pid}/notes", json={"title": "Nephrology visit", "body": "eGFR falling."})
    assert note.status_code == 200
    doc = fhir.store["DocumentReference"][note.json()["fhir_document_reference_id"]]
    assert doc["category"][0]["coding"][0]["code"] == "clinical-note" and doc["author"][0]["display"] == "Dr. Meena"
    assert [n["title"] for n in (await client.get(f"/api/profiles/{pid}/notes")).json()] == ["Nephrology visit"]
    patients = (await client.get("/api/doctor/patients")).json()
    assert patients[0]["name"] == "Rajan Subramanian" and patients[0]["critical_alerts"] == 1
    assert [p["value"] for p in patients[0]["egfr"]] == [72, 61, 52, 47]
    prof = (await client.get(f"/api/profiles/{pid}")).json()
    assert prof["access"]["can_write"] is True and prof["active_alerts"] == 4


async def test_doctor_profile_counts_respect_scope(client, db, world):  # noqa: F811
    await grant(db, world, ["labs"])
    login(client, world["doctor"])
    prof = (await client.get(f"/api/profiles/{world['pid']}")).json()
    assert prof["active_alerts"] == 0 and prof["critical_alerts"] == 0 and prof["documents"] == 0


@pytest.mark.parametrize("q", ["glyco", "Glycomet", "metformin"])
async def test_drug_search(client, db, q):
    u = await make_user(db, email="d@x.com", role="doctor", doctor_status="verified")
    login(client, u)
    hits = (await client.get(f"/api/drugs?q={q}")).json()
    assert any(h["generic"] == "metformin" for h in hits)


async def test_patient_explainer_is_grounded_in_one_document(client, db, world, monkeypatch):  # noqa: F811
    seen = {}

    async def fake_text(*, purpose, system, contents, **kw):
        seen["system"] = system
        key = next(ln.split("]")[0][1:] for ln in system.splitlines() if ln.startswith("[Observation/"))
        return f"Your kidney test is lower than normal [{key}]. Ask about [MedicationRequest/999]."

    monkeypatch.setattr("app.ai.client.generate_text", fake_text)
    login(client, world["owner"])
    docs = (await client.get(f"/api/profiles/{world['pid']}/documents")).json()
    lab = next(d for d in docs if d["original_filename"] == "medline_2026-08-05_lab.pdf")
    resp = await client.post(f"/api/documents/{lab['id']}/explain", json={"language": "Tamil"})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["language"] == "Tamil" and "Tamil" in seen["system"]
    assert [c["key"] for c in body["citations"] if not c.get("unknown")][0].startswith("Observation/")
    assert any(c.get("unknown") and c["key"] == "MedicationRequest/999" for c in body["citations"])
    # Only this report's facts reach the model: no medicines, allergies or other labs' values.
    assert "eGFR 47" in seen["system"]
    for forbidden in ("Penicillin", "Glycomet", "Novamox", "eGFR 72", "eGFR 61"):
        assert forbidden not in seen["system"], forbidden
    assert (await client.post(f"/api/documents/{lab['id']}/explain", json={"language": "French"})).status_code == 422
    # Doctors, even with full consent, use the copilot instead.
    await grant(db, world, ALL_FOUR + ["documents"])
    login(client, world["doctor"])
    assert (await client.post(f"/api/documents/{lab['id']}/explain", json={})).status_code == 403
