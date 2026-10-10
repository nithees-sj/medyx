"""Stage 5: decide which extracted items are new and which merge into the existing record.

Rules (spec §7.5):
- Observation: same LOINC + same date (±1 day) + value within 2% → same Observation.
- MedicationRequest: same generic + same organization + same start date → same order.
- Condition: same ICD-10 code → same Condition (text match when uncoded).
- AllergyIntolerance: same allergy class / substance → same allergy.
A merge adds an extra Provenance to the existing resource instead of creating a new one.
"""

from dataclasses import dataclass
from datetime import date
from typing import Any

from rapidfuzz import fuzz

from app import knowledge as kb
from app.services.record import PatientRecord


@dataclass
class Planned:
    item_id: Any
    kind: str  # Condition | MedicationRequest | AllergyIntolerance | Observation | Vital
    normalized: dict[str, Any]
    raw: dict[str, Any]
    existing_ref: str | None = None  # set when this item merges into an existing resource
    batch_key: int | None = None  # index of an earlier item in this batch it duplicates


def same_org(a: str | None, b: str | None) -> bool:
    if not a or not b:
        return False
    return fuzz.token_set_ratio(kb.norm_text(a), kb.norm_text(b)) >= 90


def _d(v: str | None) -> date | None:
    return date.fromisoformat(v) if v else None


def _close(a: float | None, b: float | None) -> bool:
    if a is None or b is None:
        return False
    if a == b:
        return True
    return abs(a - b) <= 0.02 * max(abs(a), abs(b))


def _obs_match(n: dict[str, Any], loinc: str | None, value: float | None, eff: date | None) -> bool:
    if not loinc or n.get("loinc") != loinc or eff is None or not n.get("effective_date"):
        return False
    d = _d(n["effective_date"])
    return d is not None and abs((d - eff).days) <= 1 and _close(n.get("value"), value)


def find_existing(record: PatientRecord, kind: str, n: dict[str, Any], org: str | None) -> str | None:
    if kind == "Observation":
        for o in record.observations:
            if o.category == "laboratory" and _obs_match(n, o.loinc, o.value, o.effective):
                return o.ref
    elif kind == "Vital":
        for o in record.observations:
            if o.category != "vital-signs" or o.loinc != n.get("loinc") or o.effective != _d(n.get("effective_date")):
                continue
            if n["key"] == "bp" and o.value_text.startswith(f"{int(n['systolic'])}/{int(n['diastolic'])}"):
                return o.ref
            if n["key"] != "bp" and _close(o.value, n.get("value")):
                return o.ref
    elif kind == "MedicationRequest":
        for m in record.medications:
            if m.generic == n["generic"] and same_org(m.org, org) and m.start == _d(n.get("start_date")):
                return m.ref
    elif kind == "Condition":
        for c in record.conditions:
            if n.get("icd10") and c.icd10 == n["icd10"]:
                return c.ref
            if not n.get("icd10") and kb.norm_text(c.text) == kb.norm_text(n["text"]):
                return c.ref
    elif kind == "AllergyIntolerance":
        for a in record.allergies:
            if n.get("allergy_class") and a.allergy_class == n["allergy_class"]:
                return a.ref
            if kb.norm_text(a.substance) == kb.norm_text(n["substance"]):
                return a.ref
    return None


def _dupe_in_batch(kind: str, n: dict[str, Any], earlier: list[Planned]) -> int | None:
    for i, p in enumerate(earlier):
        if p.kind != kind or p.existing_ref or p.batch_key is not None:
            continue
        m = p.normalized
        if kind == "Observation" and _obs_match(n, m.get("loinc"), m.get("value"), _d(m.get("effective_date"))):
            return i
        if kind == "MedicationRequest" and m["generic"] == n["generic"] and m.get("start_date") == n.get("start_date"):
            return i
        if kind == "Condition" and (
            (n.get("icd10") and m.get("icd10") == n["icd10"]) or kb.norm_text(m["text"]) == kb.norm_text(n["text"])
        ):
            return i
        if kind == "AllergyIntolerance" and (
            (n.get("allergy_class") and m.get("allergy_class") == n["allergy_class"])
            or kb.norm_text(m["substance"]) == kb.norm_text(n["substance"])
        ):
            return i
    return None


def plan(record: PatientRecord, items: list[Planned], org: str | None) -> list[Planned]:
    """Annotate each item with its merge target (existing resource or earlier batch item)."""
    out: list[Planned] = []
    for p in items:
        p.existing_ref = find_existing(record, p.kind, p.normalized, org)
        if p.existing_ref is None:
            p.batch_key = _dupe_in_batch(p.kind, p.normalized, out)
        out.append(p)
    return out
