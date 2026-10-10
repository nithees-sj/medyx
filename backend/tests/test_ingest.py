"""Ingest pipeline tests. FHIR is the in-memory fake; the AI boundary is stubbed with real saved outputs."""

import json
from pathlib import Path

import pytest
from sqlalchemy import select

from app.ai.client import AIError
from app.models import Document, ExtractionItem, HealthProfile
from app.services import record as record_service
from app.services.ingest import extract as extract_mod
from app.services.ingest import pipeline
from app.services.ingest.schemas import ExtractionResult
from tests.conftest import login, make_user

ROOT = Path(__file__).resolve().parents[2]
FIXTURES = Path(__file__).parent / "fixtures" / "extractions"


def fixture_result(stem: str) -> ExtractionResult:
    return ExtractionResult.model_validate_json((FIXTURES / f"{stem}.json").read_text())


@pytest.fixture(autouse=True)
def _isolate(settings, tmp_path, monkeypatch):
    settings.storage_dir = tmp_path / "storage"
    settings.demo_cache_dir = tmp_path / "cache"
    record_service.invalidate()
    # Uploads are processed explicitly in tests, not by the background worker.
    monkeypatch.setattr(pipeline.worker, "enqueue", lambda doc_id: None)


@pytest.fixture
def stub_extraction(monkeypatch):
    """Map uploaded file name → saved real extraction."""

    async def fake_extract(data, mime, sha256):
        doc_name = fake_extract.names[sha256]
        return fixture_result(doc_name), "ai"

    fake_extract.names = {}
    monkeypatch.setattr(pipeline, "extract_document", fake_extract)
    return fake_extract


async def create_owner_with_profile(client, db):
    owner = await make_user(db, email="priya@x.com", role="patient", name="Priya Rajan")
    login(client, owner)
    resp = await client.post(
        "/api/profiles",
        json={"display_name": "Rajan Subramanian", "relationship": "parent", "dob": "1962-05-14", "sex": "male"},
    )
    assert resp.status_code == 201
    return owner, resp.json()["id"]


async def upload(client, profile_id, paths, stub):
    import hashlib

    files = []
    for p in paths:
        data = p.read_bytes()
        stub.names[hashlib.sha256(data).hexdigest()] = p.stem
        files.append(("files", (p.name, data)))
    resp = await client.post(f"/api/profiles/{profile_id}/documents", files=files)
    assert resp.status_code == 200, resp.text
    return resp.json()


def demo(name: str) -> Path:
    return next((ROOT / "demo_data").rglob(name))


async def test_upload_validation_and_duplicates(client, db, stub_extraction):
    _, pid = await create_owner_with_profile(client, db)
    bad = await client.post(f"/api/profiles/{pid}/documents", files=[("files", ("notes.txt", b"hello world"))])
    assert bad.json()[0]["error"] == "notes.txt isn't a PDF, JPG or PNG"
    big = await client.post(
        f"/api/profiles/{pid}/documents", files=[("files", ("huge.pdf", b"%PDF-1.4" + b"0" * (15 * 1024 * 1024)))]
    )
    assert "larger than 15 MB" in big.json()[0]["error"]
    first = await upload(client, pid, [demo("sunrise_2024-03-12_lab.pdf")], stub_extraction)
    assert first[0]["document"]["label"] == "D1" and not first[0]["duplicate"]
    again = await upload(client, pid, [demo("sunrise_2024-03-12_lab.pdf")], stub_extraction)
    assert again[0]["duplicate"] is True


async def test_pipeline_writes_fhir_with_provenance_and_merges(client, db, fhir, stub_extraction):
    _, pid = await create_owner_with_profile(client, db)
    up = await upload(
        client, pid, [demo("sunrise_2024-03-12_lab.pdf"), demo("sunrise_2024-03-12_opd.pdf")], stub_extraction
    )
    for r in up:
        await pipeline.process_document(r["document"]["id"])

    docs = (await db.scalars(select(Document).order_by(Document.seq))).all()
    assert [d.status for d in docs] == ["done", "needs_review"]  # the year-only allergy waits for review
    assert docs[0].source_org_name == "Sunrise Diabetes & Multispeciality Hospital"
    assert docs[1].result_counts["merged"] == 1  # HbA1c in the OPD note == HbA1c in the lab report

    obs = list(fhir.store["Observation"].values())
    hba1c = [o for o in obs if o["code"].get("coding", [{}])[0].get("code") == "4548-4"]
    assert len(hba1c) == 1
    provs = [
        p for p in fhir.store["Provenance"].values() if p["target"][0]["reference"] == f"Observation/{hba1c[0]['id']}"
    ]
    assert len(provs) == 2
    assert {e["url"].rsplit("/", 1)[-1] for e in provs[0]["entity"][0]["extension"]} == {
        "source-page",
        "source-snippet",
    }
    assert "AllergyIntolerance" not in fhir.store  # pending items are not written

    profile = await db.get(HealthProfile, docs[0].profile_id)
    await db.refresh(profile)
    assert profile.record_version == 2  # one bump per written document


async def test_review_confirm_writes_pending_item(client, db, fhir, stub_extraction):
    _, pid = await create_owner_with_profile(client, db)
    up = await upload(client, pid, [demo("sunrise_2024-03-12_opd.pdf")], stub_extraction)
    await pipeline.process_document(up[0]["document"]["id"])
    queue = (await client.get(f"/api/profiles/{pid}/review")).json()
    assert [q["resource_type"] for q in queue] == ["AllergyIntolerance"]
    resp = await client.post(f"/api/review/{queue[0]['id']}", json={"action": "confirm"})
    assert resp.status_code == 200 and resp.json()["document_status"] == "done"
    allergy = next(iter(fhir.store["AllergyIntolerance"].values()))
    assert allergy["code"]["text"] == "Penicillin"
    again = await client.post(f"/api/review/{queue[0]['id']}", json={"action": "confirm"})
    assert again.status_code == 409


async def test_review_correct_and_reject(client, db, fhir, stub_extraction):
    _, pid = await create_owner_with_profile(client, db)
    up = await upload(client, pid, [demo("sunrise_2024-03-12_opd.pdf")], stub_extraction)
    await pipeline.process_document(up[0]["document"]["id"])
    item = (await client.get(f"/api/profiles/{pid}/review")).json()[0]
    bad = await client.post(f"/api/review/{item['id']}", json={"action": "correct", "fields": {"value": 3}})
    assert bad.status_code == 422
    ok = await client.post(f"/api/review/{item['id']}", json={"action": "correct", "fields": {"reaction": "urticaria"}})
    assert ok.json()["status"] == "corrected"
    allergy = next(iter(fhir.store["AllergyIntolerance"].values()))
    assert allergy["reaction"][0]["manifestation"][0]["text"] == "urticaria"


async def test_full_rajan_record_is_merged_into_one_thread(client, db, fhir, stub_extraction):
    _, pid = await create_owner_with_profile(client, db)
    paths = sorted((ROOT / "demo_data" / "rajan").iterdir())
    up = await upload(client, pid, paths, stub_extraction)
    for r in up:
        await pipeline.process_document(r["document"]["id"])
    profile = await db.get(HealthProfile, pid)
    await db.refresh(profile)
    record = await record_service.load_record(db, profile)
    egfr = record.series("33914-3")
    assert [(o.effective.isoformat(), o.value) for o in egfr] == [
        ("2024-03-12", 72),
        ("2025-01-20", 61),
        ("2026-01-15", 52),
        ("2026-08-05", 47),
    ]
    assert [o.value for o in record.series("2160-0")] == [1.0, 1.2, 1.4, 1.5]
    assert sorted(m.generic for m in record.medications) == [
        "amoxicillin",
        "aspirin",
        "dextromethorphan",
        "metformin",
        "metformin",
        "paracetamol",
        "ramipril",
    ]
    assert all(o.sources for o in record.observations)
    assert {s.page for o in egfr for s in o.sources} == {1}


async def test_demo_cache_used_only_for_known_files(settings, monkeypatch, tmp_path):
    settings.demo_cache = True

    async def boom(**kwargs):
        raise AIError("AI service unavailable (ConnectError)")

    monkeypatch.setattr(extract_mod.ai, "generate_structured", boom)
    cached = fixture_result("medline_2026-08-05_lab")
    settings.demo_cache_dir.mkdir(parents=True)
    (settings.demo_cache_dir / "abc.json").write_text(cached.model_dump_json())
    result, source = await extract_mod.extract_document(b"x", "application/pdf", "abc")
    assert source == "cache" and result.labs[0].value == 133
    with pytest.raises(extract_mod.ExtractionFailed):
        await extract_mod.extract_document(b"x", "application/pdf", "unknown-hash")
    settings.demo_cache = False
    with pytest.raises(extract_mod.ExtractionFailed):
        await extract_mod.extract_document(b"x", "application/pdf", "abc")


async def test_successful_extraction_is_saved_to_cache(settings, monkeypatch):
    result = fixture_result("citydx_2026-01-15_lab")

    async def ok(**kwargs):
        return result

    monkeypatch.setattr(extract_mod.ai, "generate_structured", ok)
    _, source = await extract_mod.extract_document(b"x", "application/pdf", "hash1")
    assert source == "ai"
    assert json.loads((settings.demo_cache_dir / "hash1.json").read_text())["labs"][0]["value"] == 1.4


async def test_failed_extraction_marks_document_failed(client, db, monkeypatch):
    _, pid = await create_owner_with_profile(client, db)

    async def fail(data, mime, sha256):
        raise extract_mod.ExtractionFailed("Couldn't read this document: AI service error (500)")

    monkeypatch.setattr(pipeline, "extract_document", fail)
    resp = await client.post(
        f"/api/profiles/{pid}/documents", files=[("files", ("x.pdf", demo("medline_2026-08-05_lab.pdf").read_bytes()))]
    )
    doc_id = resp.json()[0]["document"]["id"]
    await pipeline.process_document(doc_id)
    d = (await client.get(f"/api/documents/{doc_id}")).json()
    assert d["status"] == "failed" and "AI service error" in d["error"]
    items = (await db.scalars(select(ExtractionItem))).all()
    assert items == []


async def test_strangers_cannot_upload_or_read(client, db, stub_extraction):
    _, pid = await create_owner_with_profile(client, db)
    up = await upload(client, pid, [demo("medline_2026-08-05_lab.pdf")], stub_extraction)
    doc_id = up[0]["document"]["id"]
    other = await make_user(db, email="other@x.com", role="patient")
    doc = await make_user(db, email="doc@x.com", role="doctor", doctor_status="verified")
    for u in (other, doc):
        login(client, u)
        assert (await client.get(f"/api/documents/{doc_id}/file")).status_code == 403
        assert (await client.get(f"/api/profiles/{pid}/documents")).status_code == 403
        r = await client.post(f"/api/profiles/{pid}/documents", files=[("files", ("a.pdf", b"%PDF-1.4"))])
        assert r.status_code == 403


async def test_timeline_trends_medications_and_stop(client, db, fhir, stub_extraction):
    _, pid = await create_owner_with_profile(client, db)
    paths = sorted((ROOT / "demo_data" / "rajan").iterdir())
    for r in await upload(client, pid, paths, stub_extraction):
        await pipeline.process_document(r["document"]["id"])

    orgs = (await client.get(f"/api/profiles/{pid}/orgs")).json()
    assert list(orgs)[:2] == ["Sunrise Diabetes & Multispeciality Hospital", "Lakeview Heart Institute"]
    assert len(set(orgs.values())) == len(orgs) == 5

    tl = (await client.get(f"/api/profiles/{pid}/timeline")).json()
    groups = {g["id"]: sum(1 for i in tl["items"] if i["group"] == g["id"]) for g in tl["groups"]}
    assert (
        groups["medications"] == 7 and groups["documents"] == 9 and groups["labs"] == 14
    )  # 4 + 4 + 3 + 3 (the OPD HbA1c merged)
    assert all(i["sources"] for i in tl["items"] if i["group"] != "documents")

    trends = (await client.get(f"/api/profiles/{pid}/trends")).json()["analytes"]
    egfr = next(a for a in trends if a["loinc"] == "33914-3")
    assert [p["value"] for p in egfr["points"]] == [72, 61, 52, 47]
    assert len({p["org"] for p in egfr["points"]}) == 4

    meds = (await client.get(f"/api/profiles/{pid}/medications")).json()["medications"]
    glucophage = next(m for m in meds if m["brand"] == "Glucophage")
    assert glucophage["status"] == "active"
    stopped = await client.post(f"/api/profiles/{pid}/medications/stop", json={"ref": glucophage["ref"]})
    assert stopped.status_code == 200
    meds = (await client.get(f"/api/profiles/{pid}/medications")).json()["medications"]
    assert next(m for m in meds if m["brand"] == "Glucophage")["status"] == "stopped"
