"""Shared types for safety rules. Rules are pure functions of the record and a date."""

import hashlib
from dataclasses import dataclass, field
from typing import Any

from app.services.record import Allergy, Medication, Observation


@dataclass
class Evidence:
    ref: str
    kind: str  # medication | allergy | observation | condition
    label: str
    date: str | None
    org: str | None
    document_id: str | None = None
    doc_label: str | None = None
    page: int | None = None
    snippet: str | None = None

    def json(self) -> dict[str, Any]:
        return self.__dict__.copy()


@dataclass
class Finding:
    rule_id: str
    type: str
    severity: str  # info | warning | critical
    title: str
    evidence: list[Evidence]
    facts: dict[str, Any] = field(default_factory=dict)  # input for explanations
    details: dict[str, Any] = field(default_factory=dict)  # e.g. drift fit, shown in the UI
    patient_text: str = ""
    clinical_text: str = ""

    def fingerprint(self, profile_id: str) -> str:
        key = "|".join([profile_id, self.rule_id, *sorted(e.ref for e in self.evidence)])
        return hashlib.sha256(key.encode()).hexdigest()


def _first_source(x: Any) -> tuple[str | None, str | None, int | None, str | None]:
    s = x.sources[0] if getattr(x, "sources", None) else None
    return (s.document_id, s.doc_label, s.page, s.snippet) if s else (None, None, None, None)


def med_evidence(m: Medication) -> Evidence:
    doc, label, page, snippet = _first_source(m)
    name = m.display + (f" ({m.brand})" if m.brand else "")
    return Evidence(
        m.ref, "medication", name, m.start.isoformat() if m.start else None, m.org, doc, label, page, snippet
    )


def allergy_evidence(a: Allergy) -> Evidence:
    doc, label, page, snippet = _first_source(a)
    name = a.substance + (f" — {a.reaction}" if a.reaction else "")
    return Evidence(
        a.ref, "allergy", name, a.recorded.isoformat() if a.recorded else None, a.org, doc, label, page, snippet
    )


def obs_evidence(o: Observation) -> Evidence:
    doc, label, page, snippet = _first_source(o)
    return Evidence(
        o.ref,
        "observation",
        f"{o.name} {o.value_text}",
        o.effective.isoformat() if o.effective else None,
        o.org,
        doc,
        label,
        page,
        snippet,
    )


def molecules(generic: str) -> set[str]:
    return {p.strip() for p in generic.split(" + ") if p.strip()}


DISCLAIMER = "Please discuss this with a doctor before changing any medicine."
