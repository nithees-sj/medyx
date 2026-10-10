"""Phase 3 acceptance checks against HAPI + the API (run after e2e/ingest_check.py)."""

import sys

import httpx

API = "http://localhost:8000/api"
FHIR = "http://localhost:8080/fhir"
H = {"X-HT-Request": "1", "Cache-Control": "no-cache"}
ok = True


def check(cond: bool, msg: str) -> None:
    global ok
    print(("PASS " if cond else "FAIL ") + msg)
    ok = ok and cond


def search(path: str) -> list[dict]:
    b = httpx.get(f"{FHIR}/{path}", headers=H, timeout=30).json()
    return [e["resource"] for e in b.get("entry", [])]


c = httpx.Client(base_url=API, headers=H, timeout=60)
c.post("/auth/demo", json={"persona": "priya"}).raise_for_status()
profile = next(p for p in c.get("/profiles").json() if p["display_name"] == sys.argv[1] if len(sys.argv) > 1) if len(
    sys.argv
) > 1 else next(p for p in c.get("/profiles").json() if p["display_name"] == "Rajan Subramanian")
fhir_pid = c.get(f"/profiles/{profile['id']}/export").json()["entry"][0]["resource"]["id"]
pref = f"Patient/{fhir_pid}"

# 1. eGFR series
egfr = search(f"Observation?subject={pref}&code=http://loinc.org|33914-3&_count=50")
series = sorted((o["effectiveDateTime"], o["valueQuantity"]["value"], o["code"]["text"]) for o in egfr)
print("   eGFR:", series)
check(len(series) == 4 and [v for _, v, _ in series] == [72, 61, 52, 47], "all four eGFR values in one LOINC 33914-3 series")
check(len({t for _, _, t in series}) == 3, "eGFR came from 3 different test names")

# 2. Creatinine SI conversion
creat = search(f"Observation?subject={pref}&code=http://loinc.org|2160-0&_count=50")
cs = sorted((o["effectiveDateTime"], o["valueQuantity"]["value"], o["valueQuantity"]["unit"]) for o in creat)
print("   creatinine:", cs)
medline = [o for o in creat if o["effectiveDateTime"] == "2026-08-05"]
check(
    len(medline) == 1 and medline[0]["valueQuantity"]["value"] == 1.5 and medline[0]["valueQuantity"]["code"] == "mg/dL",
    "133 µmol/L stored as 1.50 mg/dL",
)
written = [e.get("valueString") for e in medline[0].get("extension", []) if e["url"].endswith("written-text")]
check(written == ["133 µmol/L"], f"original value kept in written-text extension ({written})")

# 3. Brands → generics
meds = search(f"MedicationRequest?subject={pref}&_count=50")
gen = sorted(
    (
        m["medicationCodeableConcept"]["coding"][0]["code"],
        next((e["valueString"] for e in m.get("extension", []) if e["url"].endswith("brand-name")), None),
        m["status"],
    )
    for m in meds
)
print("   meds:", gen)
expected = {
    ("amoxicillin", "Novamox"),
    ("aspirin", "Ecosprin"),
    ("dextromethorphan", None),
    ("metformin", "Glucophage"),
    ("metformin", "Glycomet"),
    ("paracetamol", "Dolo 650"),
    ("ramipril", "Cardace"),
}
check({(g, b) for g, b, _ in gen} == expected, "brands mapped to generics (brand kept in extension)")

# 4. Provenance for every clinical resource, pointing at a DocumentReference with a page
clinical = (
    search(f"Condition?subject={pref}&_count=100")
    + search(f"Observation?subject={pref}&_count=200")
    + meds
    + search(f"AllergyIntolerance?patient={pref}&_count=50")
)
missing = []
for r in clinical:
    provs = search(f"Provenance?target={r['resourceType']}/{r['id']}")
    good = [
        p
        for p in provs
        for ent in p.get("entity", [])
        if ent["what"]["reference"].startswith("DocumentReference/")
        and any(x["url"].endswith("source-page") for x in ent.get("extension", []))
    ]
    if not good:
        missing.append(f"{r['resourceType']}/{r['id']}")
check(not missing, f"every one of {len(clinical)} resources has Provenance → DocumentReference + page {missing[:5]}")
hba1c_0312 = [o for o in search(f"Observation?subject={pref}&code=http://loinc.org|4548-4") if o["effectiveDateTime"] == "2024-03-12"]
provs = search(f"Provenance?target=Observation/{hba1c_0312[0]['id']}") if hba1c_0312 else []
check(len(hba1c_0312) == 1 and len(provs) == 2, "HbA1c in OPD note + lab report merged into one Observation with 2 Provenance")

# 5. Export bundle
bundle = c.get(f"/profiles/{profile['id']}/export").json()
types = sorted({e["resource"]["resourceType"] for e in bundle["entry"]})
print("   export types:", types, "entries:", len(bundle["entry"]))
check(bundle["type"] == "collection" and "Provenance" in types and "Patient" in types, "export is a collection Bundle")
try:
    from fhir.resources.R4B.bundle import Bundle

    Bundle.model_validate(bundle)
    check(True, "export Bundle validates against FHIR R4B models")
except Exception as e:  # noqa: BLE001
    check(False, f"export Bundle validation: {str(e)[:300]}")

sys.exit(0 if ok else 1)
