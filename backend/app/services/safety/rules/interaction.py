"""Curated drug–drug interactions between medicines active at the same time."""

from datetime import date
from typing import Any

from app import knowledge as kb
from app.services.record import Medication, PatientRecord
from app.services.safety.findings import Finding, med_evidence, molecules


def _matches(m: Medication, side: dict[str, Any]) -> bool:
    return bool(
        molecules(m.generic) & set(side.get("molecules", []))
        or m.generic in side.get("molecules", [])
        or m.classes & set(side.get("classes", []))
    )


def evaluate(record: PatientRecord, today: date) -> list[Finding]:
    active = [m for m in record.medications if m.active_on(today)]
    findings: list[Finding] = []
    seen: set[tuple[str, frozenset[str]]] = set()
    for it in kb.load("interactions")["interactions"]:
        for a in active:
            if not _matches(a, it["a"]):
                continue
            for b in active:
                if b.ref == a.ref or not _matches(b, it["b"]):
                    continue
                key = (it["id"], frozenset({a.ref, b.ref}))
                if key in seen:
                    continue
                seen.add(key)
                findings.append(
                    Finding(
                        rule_id=f"interaction:{it['id']}",
                        type="interaction",
                        severity=it.get("severity", "warning"),
                        title=f"Interaction: {a.generic} + {b.generic} — risk of {it['effect']}",
                        evidence=[med_evidence(a), med_evidence(b)],
                        facts={
                            "drug_a": a.display,
                            "drug_a_source": a.org,
                            "drug_b": b.display,
                            "drug_b_source": b.org,
                            "effect": it["effect"],
                        },
                    )
                )
    return findings
