"""Unit tests for each safety rule (positive and negative), on hand-built records."""

import uuid
from datetime import date

from app import knowledge as kb
from app.services.record import Allergy, Medication, Observation, PatientRecord
from app.services.safety import engine
from app.services.safety.explain import DISCLAIMER, apply_templates
from app.services.safety.rules import allergy_conflict, cascade, duplicate_therapy, interaction, lab_drift

TODAY = date(2026, 10, 10)
_n = iter(range(1, 10_000))


def med(generic, start, end=None, org="Clinic A", brand=None, mg=None, status="active") -> Medication:
    return Medication(
        ref=f"MedicationRequest/{next(_n)}",
        generic=generic,
        display=generic.title(),
        brand=brand,
        classes=kb.classes_for(generic, mg),
        strength=None,
        strength_mg=mg,
        frequency_label="1-0-1",
        frequency_text="1-0-1",
        per_day=2,
        as_needed=False,
        instructions=None,
        start=date.fromisoformat(start),
        end=date.fromisoformat(end) if end else None,
        fhir_status=status,
        org=org,
        requester=None,
        written_text=None,
    )


def obs(loinc, day, value, org="Lab", low=None, high=None) -> Observation:
    return Observation(
        ref=f"Observation/{next(_n)}",
        loinc=loinc,
        name=kb.lab_by_code(loinc).short,
        category="laboratory",
        value=value,
        value_text=f"{value}",
        unit=None,
        unit_display="",
        decimals=1,
        effective=date.fromisoformat(day),
        interpretation=None,
        ref_low=low,
        ref_high=high,
        org=org,
        written_text=None,
    )


def allergy(substance) -> Allergy:
    return Allergy(
        ref=f"AllergyIntolerance/{next(_n)}",
        substance=substance,
        allergy_class=kb.allergy_class_for(substance),
        reaction="rash",
        criticality=None,
        recorded=date(2022, 1, 1),
        org="Hospital",
    )


def record(meds=(), labs=(), allergies=()) -> PatientRecord:
    return PatientRecord(
        profile_id=uuid.uuid4(),
        version=1,
        patient_ref="Patient/1",
        display_name="Test",
        dob=date(1960, 1, 1),
        sex="male",
        blood_group="B+",
        medications=list(meds),
        observations=list(labs),
        allergies=list(allergies),
    )


# ─── duplicate therapy ───


def test_duplicate_same_molecule_different_brands_and_orgs():
    r = record(
        [
            med("metformin", "2024-03-12", brand="Glycomet", org="Sunrise"),
            med("metformin", "2025-09-10", brand="Glucophage", org="Anand"),
        ]
    )
    f = duplicate_therapy.evaluate(r, TODAY)
    assert len(f) == 1 and f[0].severity == "warning" and f[0].type == "duplicate_therapy"
    assert "metformin" in f[0].title and "Glycomet" in f[0].title and "Glucophage" in f[0].title


def test_duplicate_same_class():
    f = duplicate_therapy.evaluate(record([med("ramipril", "2025-01-01"), med("enalapril", "2025-06-01")]), TODAY)
    assert len(f) == 1 and f[0].rule_id == "duplicate_therapy:class:ace_inhibitor"


def test_duplicate_inside_combination_product():
    f = duplicate_therapy.evaluate(
        record([med("paracetamol", "2026-01-01"), med("ibuprofen + paracetamol", "2026-01-05")]), TODAY
    )
    assert len(f) == 1 and f[0].rule_id == "duplicate_therapy:paracetamol"


def test_no_duplicate_when_one_course_finished_or_stopped():
    r = record([med("metformin", "2024-01-01"), med("metformin", "2024-02-01", end="2024-03-01")])
    assert duplicate_therapy.evaluate(r, TODAY) == []
    r = record([med("metformin", "2024-01-01"), med("metformin", "2025-02-01", status="stopped")])
    assert duplicate_therapy.evaluate(r, TODAY) == []
    r = record([med("ramipril", "2025-01-01"), med("telmisartan", "2025-06-01")])  # ACEi + ARB is not same-class
    assert duplicate_therapy.evaluate(r, TODAY) == []


# ─── allergy conflict ───


def test_penicillin_allergy_vs_amoxicillin_even_if_course_finished():
    r = record([med("amoxicillin", "2026-02-18", end="2026-02-22", brand="Novamox")], allergies=[allergy("Penicillin")])
    f = allergy_conflict.evaluate(r, TODAY)
    assert len(f) == 1 and f[0].severity == "critical" and "Novamox" in f[0].title


def test_class_members_and_combination_products():
    for drug in [
        "ampicillin",
        "cloxacillin",
        "piperacillin",
        "phenoxymethylpenicillin",
        "benzylpenicillin",
        "amoxicillin + clavulanate",
    ]:
        f = allergy_conflict.evaluate(record([med(drug, "2026-01-01")], allergies=[allergy("Penicillin")]), TODAY)
        assert len(f) == 1, drug


def test_no_allergy_conflict_for_unrelated_drugs():
    r = record([med("azithromycin", "2026-01-01"), med("paracetamol", "2026-01-01")], allergies=[allergy("Penicillin")])
    assert allergy_conflict.evaluate(r, TODAY) == []
    assert allergy_conflict.evaluate(record([med("amoxicillin", "2026-01-01")]), TODAY) == []


# ─── prescribing cascade ───


def test_ace_inhibitor_cough_cascade():
    r = record(
        [med("ramipril", "2025-01-20", brand="Cardace"), med("dextromethorphan", "2025-04-02", end="2025-04-08")]
    )
    f = cascade.evaluate(r, TODAY)
    assert len(f) == 1 and f[0].rule_id == "prescribing_cascade:acei_cough" and f[0].facts["days_between"] == 72


def test_ccb_oedema_and_cholinesterase_cascades():
    assert len(cascade.evaluate(record([med("amlodipine", "2025-01-01"), med("furosemide", "2025-03-01")]), TODAY)) == 1
    assert len(cascade.evaluate(record([med("donepezil", "2025-01-01"), med("oxybutynin", "2025-10-01")]), TODAY)) == 1
    assert (
        len(
            cascade.evaluate(
                record([med("metoclopramide", "2025-01-01"), med("levodopa + carbidopa", "2025-06-01")]), TODAY
            )
        )
        == 1
    )


def test_no_cascade_outside_window_before_index_or_after_index_stopped():
    assert cascade.evaluate(record([med("ramipril", "2024-01-01"), med("dextromethorphan", "2025-04-02")]), TODAY) == []
    assert cascade.evaluate(record([med("dextromethorphan", "2025-01-01"), med("ramipril", "2025-02-01")]), TODAY) == []
    r = record([med("ramipril", "2025-01-01", end="2025-02-01"), med("dextromethorphan", "2025-03-01")])
    assert cascade.evaluate(r, TODAY) == []


def test_low_dose_aspirin_started_with_bp_drug_is_not_an_nsaid_cascade():
    r = record([med("aspirin", "2025-01-20", mg=75, brand="Ecosprin"), med("ramipril", "2025-01-20")])
    assert cascade.evaluate(r, TODAY) == []
    r = record([med("ibuprofen", "2025-01-01"), med("amlodipine", "2025-02-15")])
    assert [x.rule_id for x in cascade.evaluate(r, TODAY)] == ["prescribing_cascade:nsaid_hypertension"]


# ─── interactions ───


def test_interactions():
    pairs = [
        ("ramipril", "spironolactone", "interaction:raas_potassium"),
        ("telmisartan", "potassium chloride", "interaction:raas_potassium"),
        ("warfarin", "aspirin", "interaction:warfarin_bleeding"),
        ("warfarin", "ibuprofen", "interaction:warfarin_bleeding"),
        ("clarithromycin", "simvastatin", "interaction:clarithromycin_simvastatin"),
        ("sertraline", "tramadol", "interaction:ssri_tramadol"),
    ]
    for a, b, rule in pairs:
        f = interaction.evaluate(record([med(a, "2026-01-01"), med(b, "2026-02-01")]), TODAY)
        assert [x.rule_id for x in f] == [rule], (a, b)


def test_no_interaction_when_not_concurrent_or_unrelated():
    r = record([med("clarithromycin", "2025-01-01", end="2025-01-07"), med("simvastatin", "2026-01-01")])
    assert interaction.evaluate(r, TODAY) == []
    assert (
        interaction.evaluate(record([med("ramipril", "2026-01-01"), med("aspirin", "2026-01-01", mg=75)]), TODAY) == []
    )


# ─── lab drift ───

EGFR, CREAT, HBA1C, K = "33914-3", "2160-0", "4548-4", "2823-3"


def rajan_kidney(with_metformin=True):
    labs = [
        obs(EGFR, "2024-03-12", 72, "Sunrise", low=60),
        obs(EGFR, "2025-01-20", 61, "Lakeview", low=60),
        obs(EGFR, "2026-01-15", 52, "City Dx", low=60),
        obs(EGFR, "2026-08-05", 47, "Medline", low=60),
        obs(CREAT, "2024-03-12", 1.0),
        obs(CREAT, "2025-01-20", 1.2),
        obs(CREAT, "2026-01-15", 1.4),
        obs(CREAT, "2026-08-05", 1.5),
    ]
    meds = [med("metformin", "2024-03-12")] if with_metformin else []
    return record(meds, labs)


def test_egfr_drift_with_metformin_is_one_grouped_alert():
    f = lab_drift.evaluate(rajan_kidney(), TODAY)
    assert len(f) == 1
    a = f[0]
    assert a.rule_id == "lab_drift:kidney:metformin" and a.severity == "warning"
    assert "metformin" in a.title and "review metformin dose" in a.title
    series = a.details["series"]
    assert set(series) == {EGFR, CREAT}
    assert -11 < series[EGFR]["slope_per_year"] < -9.5
    assert series[EGFR]["projected_cross_date"].startswith("2026-09")
    assert sum(e.kind == "medication" for e in a.evidence) == 1


def test_drift_fires_even_when_all_values_in_range():
    labs = [
        obs(EGFR, "2023-01-01", 110, low=60),
        obs(EGFR, "2024-01-01", 100, low=60),
        obs(EGFR, "2025-01-01", 90, low=60),
    ]
    f = lab_drift.evaluate(record(labs=labs), TODAY)
    assert len(f) == 1 and f[0].facts["analytes"][0]["all_within_reference_range"] is True
    assert "metformin" not in f[0].title


def test_no_drift_for_improving_stable_short_or_sparse_series():
    improving = [obs(HBA1C, "2024-03-12", 7.8), obs(HBA1C, "2025-01-20", 7.2), obs(HBA1C, "2026-01-15", 7.0)]
    stable = [obs(EGFR, "2024-01-01", 80), obs(EGFR, "2025-01-01", 79), obs(EGFR, "2026-01-01", 80)]
    short = [obs(EGFR, "2026-01-01", 72), obs(EGFR, "2026-02-01", 61), obs(EGFR, "2026-03-01", 52)]  # < 180 days
    sparse = [obs(K, "2025-01-20", 4.6), obs(K, "2026-08-05", 5.0)]  # < 3 points
    for labs in (improving, stable, short, sparse):
        assert lab_drift.evaluate(record(labs=labs), TODAY) == []


def test_metformin_with_low_egfr_without_drift_and_critical_below_30():
    labs = [obs(EGFR, "2026-01-01", 42)]
    f = lab_drift.evaluate(record([med("metformin", "2025-01-01")], labs), TODAY)
    assert len(f) == 1 and f[0].rule_id == "lab_drift:metformin_egfr" and f[0].severity == "warning"
    f = lab_drift.evaluate(record([med("metformin", "2025-01-01")], [obs(EGFR, "2026-01-01", 28)]), TODAY)
    assert f[0].severity == "critical"
    assert lab_drift.evaluate(record([], labs), TODAY) == []


# ─── engine + explanations + draft check ───


def test_templates_end_with_disclaimer():
    r = rajan_kidney()
    r.medications += [med("amoxicillin", "2026-02-18", end="2026-02-22")]
    r.allergies = [allergy("Penicillin")]
    findings = engine.run_rules(r, TODAY)
    apply_templates(findings)
    assert findings and all(f.patient_text.endswith(DISCLAIMER) for f in findings)
    assert all(f.clinical_text for f in findings)
    assert findings[0].severity == "critical"  # sorted most severe first


def test_fingerprint_is_stable_and_evidence_sensitive():
    f1 = lab_drift.evaluate(rajan_kidney(), TODAY)[0]
    f2 = lab_drift.evaluate(rajan_kidney(), TODAY)[0]
    assert f1.fingerprint("p") != f2.fingerprint("p")  # different resource ids → different evidence
    assert f1.fingerprint("p") == f1.fingerprint("p")


def test_draft_check_only_returns_alerts_involving_the_draft():
    r = record([med("metformin", "2024-03-12"), med("metformin", "2025-09-10")], allergies=[allergy("Penicillin")])
    draft = engine.draft_medication("Novamox 500", None, "1-1-1", 5, "Kaveri", TODAY)
    assert draft.generic == "amoxicillin" and draft.brand == "Novamox"
    findings = engine.check_draft(r, draft, TODAY)
    assert [f.type for f in findings] == ["allergy_conflict"]
    safe = engine.draft_medication("Azithral 500", None, "1-0-0", 3, "Kaveri", TODAY)
    assert engine.check_draft(r, safe, TODAY) == []
