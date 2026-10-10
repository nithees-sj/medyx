"""A recorded allergy vs any medicine (current or past) in the same allergy class."""

from datetime import date

from app import knowledge as kb
from app.services.record import PatientRecord
from app.services.safety.findings import Finding, allergy_evidence, med_evidence, molecules


def evaluate(record: PatientRecord, today: date) -> list[Finding]:
    findings: list[Finding] = []
    for a in record.allergies:
        if not a.allergy_class:
            continue
        cls = kb.allergy_class(a.allergy_class)
        members = set(cls["members"])
        member_classes = set(cls["member_classes"])
        for m in record.medications:
            hit = molecules(m.generic) & members or m.generic in members or m.classes & member_classes
            if not hit:
                continue
            findings.append(
                Finding(
                    rule_id=f"allergy_conflict:{a.allergy_class}",
                    type="allergy_conflict",
                    severity="critical",
                    title=f"{a.substance} allergy vs {m.generic}" + (f" ({m.brand})" if m.brand else ""),
                    evidence=[allergy_evidence(a), med_evidence(m)],
                    facts={
                        "allergy": a.substance,
                        "allergy_class": cls["display"],
                        "reaction": a.reaction,
                        "allergy_recorded": str(a.recorded) if a.recorded else None,
                        "allergy_source": a.org,
                        "medicine": m.display,
                        "brand": m.brand,
                        "medicine_source": m.org,
                        "medicine_start": str(m.start),
                        "medicine_status": m.status_on(today),
                    },
                )
            )
    return findings
