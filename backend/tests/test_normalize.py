"""Deterministic normalisation, exercised on real model outputs saved as fixtures."""

import json
from datetime import date
from pathlib import Path

import pytest

from app import knowledge as kb
from app.services.ingest import normalize as nz

FIXTURES = Path(__file__).parent / "fixtures" / "extractions"
TODAY = date(2026, 10, 10)


def fixture(name: str) -> dict:
    return json.loads((FIXTURES / f"{name}.json").read_text())


@pytest.mark.parametrize(
    "written,code",
    [
        ("S. Creatinine", "2160-0"),
        ("Creatinine, Serum", "2160-0"),
        ("Serum Creatinine", "2160-0"),
        ("Creatinine", "2160-0"),
        ("eGFR", "33914-3"),
        ("Estimated GFR (CKD-EPI)", "33914-3"),
        ("GFR, estimated", "33914-3"),
        ("eGFR (MDRD)", "33914-3"),
        ("HbA1c", "4548-4"),
        ("Glycated Haemoglobin (HbA1c)", "4548-4"),
        ("Glycosylated Hb", "4548-4"),
        ("FBS", "1558-6"),
        ("Fasting Blood Sugar", "1558-6"),
        ("Glucose fasting", "1558-6"),
        ("Potassium", "2823-3"),
        ("Haemoglobin", "718-7"),
        ("TSH (Thyroid Stimulating Hormone)", "3016-3"),
    ],
)
def test_lab_names_map_to_loinc(written, code):
    lab = kb.match_lab(written)
    assert lab is not None and lab.code == code


def test_unknown_and_lookalike_tests_stay_uncoded():
    assert kb.match_lab("Urine creatinine") is None
    assert kb.match_lab("Vitamin D (25-OH)") is None


def test_creatinine_si_units_convert_to_mg_dl():
    lab = nz.normalize_lab(fixture("medline_2026-08-05_lab")["labs"][0], date(2026, 8, 5))
    assert lab["loinc"] == "2160-0"
    assert lab["value"] == 1.50 and lab["unit"] == "mg/dL" and lab["converted"] is True
    assert lab["value_as_written"] == "133 µmol/L"
    assert lab["interpretation"] == "H"
    assert lab["reference_low"] == pytest.approx(0.724, abs=0.001)


def test_glucose_and_hba1c_conversions():
    g = nz.normalize_lab({"test_name_as_written": "FBS", "value": 7.0, "unit_as_written": "mmol/L"}, None)
    assert (g["value"], g["unit"]) == (126, "mg/dL")
    a = nz.normalize_lab({"test_name_as_written": "HbA1c", "value": 53, "unit_as_written": "mmol/mol"}, None)
    assert a["value"] == 7.0 and a["unit"] == "%"


def test_egfr_units_and_reference_ranges():
    for name in [
        "sunrise_2024-03-12_lab",
        "lakeview_2025-01-20_lab",
        "citydx_2026-01-15_lab",
        "medline_2026-08-05_lab",
    ]:
        labs = [nz.normalize_lab(x, None) for x in fixture(name)["labs"]]
        egfr = [x for x in labs if x["loinc"] == "33914-3"]
        assert len(egfr) == 1, name
        assert egfr[0]["unit"] == "mL/min/{1.73_m2}"
        assert egfr[0]["reference_low"] == 60


def test_all_four_egfr_values_share_one_code():
    values = []
    for name in [
        "sunrise_2024-03-12_lab",
        "lakeview_2025-01-20_lab",
        "citydx_2026-01-15_lab",
        "medline_2026-08-05_lab",
    ]:
        for x in fixture(name)["labs"]:
            lab = nz.normalize_lab(x, None)
            if lab["loinc"] == "33914-3":
                values.append((lab["effective_date"], lab["value"]))
    assert sorted(values) == [("2024-03-12", 72), ("2025-01-20", 61), ("2026-01-15", 52), ("2026-08-05", 47)]


@pytest.mark.parametrize(
    "brand,expected",
    [
        ("Glycomet", "metformin"),
        ("Glucophage", "metformin"),
        ("Cardace", "ramipril"),
        ("Ecosprin", "aspirin"),
        ("Novamox", "amoxicillin"),
        ("Mox", "amoxicillin"),
        ("Dolo 650", "paracetamol"),
        ("Crocin", "paracetamol"),
        ("Amlong", "amlodipine"),
        ("Thyronorm", "levothyroxine"),
    ],
)
def test_brands_map_to_generics(brand, expected):
    assert kb.resolve_drug(brand=brand, generic_from_ai=None, written_text=None).generic == expected


def test_brand_found_in_written_text_and_ai_fallback():
    assert kb.resolve_drug(brand=None, generic_from_ai=None, written_text="Tab. Dolo 650 SOS").generic == "paracetamol"
    unknown = kb.resolve_drug(brand="Zyxomab", generic_from_ai="Acetylsalicylic acid", written_text=None)
    assert unknown.generic == "aspirin"


def test_drug_classes_and_low_dose_aspirin():
    assert "ace_inhibitor" in kb.classes_for("ramipril")
    assert "penicillin" in kb.classes_for("amoxicillin")
    assert "nsaid" not in kb.classes_for("aspirin", 75)
    assert "nsaid" in kb.classes_for("aspirin", 350)
    assert "penicillin" in kb.classes_for(kb.canonical_generic("Co-amoxiclav"))


@pytest.mark.parametrize(
    "text,expected",
    [
        ("1-0-1", (1, 0, 1, 2, False)),
        ("0-1-0", (0, 1, 0, 1, False)),
        ("1 – 0 – 1", (1, 0, 1, 2, False)),
        ("½-0-½", (0.5, 0, 0.5, 1, False)),
        ("BD", (1, 0, 1, 2, False)),
        ("TDS", (1, 1, 1, 3, False)),
        ("HS", (0, 0, 1, 1, False)),
        ("SOS", (0, 0, 0, 0, True)),
    ],
)
def test_frequency_parsing(text, expected):
    f = nz.parse_frequency(text)
    assert (f["morning"], f["afternoon"], f["night"], f["per_day"], f["as_needed"]) == expected


def test_medications_from_real_extractions():
    d = date(2024, 3, 12)
    glycomet = nz.normalize_medication(fixture("sunrise_2024-03-12_opd")["medications"][0], d, TODAY)
    assert glycomet["generic"] == "metformin" and glycomet["brand"] == "Glycomet"
    assert glycomet["status"] == "active" and glycomet["end_date"] is None
    assert glycomet["frequency"]["per_day"] == 2

    novamox, dolo = (
        nz.normalize_medication(m, date(2026, 2, 18), TODAY) for m in fixture("anand_2026-02-18_rx")["medications"]
    )
    assert novamox["generic"] == "amoxicillin" and "penicillin" in novamox["classes"]
    assert novamox["end_date"] == "2026-02-22" and novamox["status"] == "completed"
    assert dolo["generic"] == "paracetamol" and dolo["frequency"]["as_needed"] is True

    ecosprin = nz.normalize_medication(fixture("lakeview_2025-01-20_cardiology")["medications"][1], None, TODAY)
    assert ecosprin["classes"] == ["antiplatelet", "salicylate"]

    dxm = nz.normalize_medication(fixture("anand_2025-04-02_rx")["medications"][0], None, TODAY)
    assert "antitussive" in dxm["classes"] and dxm["status"] == "completed"


def test_allergy_class_resolution():
    a = nz.normalize_allergy(fixture("sunrise_2024-03-12_opd")["allergies"][0], date(2024, 3, 12))
    assert a["allergy_class"] == "penicillin"
    assert a["recorded_date"] == "2022-01-01"
    assert kb.allergy_class_for("Amoxicillin") == "penicillin"
    assert kb.allergy_class_for("Sulpha drugs") == "sulfonamide"


def test_conditions_and_vitals():
    c = nz.normalize_condition({"text": "Type 2 diabetes mellitus", "icd10_guess": "e11.9"}, date(2024, 3, 12))
    assert c["icd10"] == "E11.9" and c["mental_health"] is False
    assert nz.normalize_condition({"text": "x", "icd10_guess": "not-a-code"}, None)["icd10"] is None
    bp = nz.normalize_vital({"name": "Blood pressure", "value": "158/96", "unit": "mmHg"}, date(2025, 1, 20))
    assert (bp["systolic"], bp["diastolic"]) == (158, 96)
    pulse = nz.normalize_vital({"name": "Pulse", "value": "82", "unit": "/min"}, None)
    assert pulse["value"] == 82 and pulse["loinc"] == "8867-4"


def test_reference_range_parsing():
    assert nz.parse_reference_range("0.7 - 1.3") == (0.7, 1.3)
    assert nz.parse_reference_range("64 – 104 µmol/L") == (64, 104)
    assert nz.parse_reference_range("> 60") == (60, None)
    assert nz.parse_reference_range("<5.7") == (None, 5.7)
