"""Prescribing cascades: a new drug that may be treating a side effect of an earlier one."""

from datetime import date

from app import knowledge as kb
from app.services.record import PatientRecord
from app.services.safety.findings import Finding, med_evidence


def evaluate(record: PatientRecord, today: date) -> list[Finding]:
    findings: list[Finding] = []
    for c in kb.load("cascades")["cascades"]:
        index_meds = [m for m in record.medications if c["index_class"] in m.classes and m.start]
        marker_meds = [m for m in record.medications if c["marker_class"] in m.classes and m.start]
        for idx in index_meds:
            for mk in marker_meds:
                if mk.ref == idx.ref or not (idx.start and mk.start):
                    continue
                gap = (mk.start - idx.start).days
                # Marker must start strictly after the index drug, within the window, while the index is still taken.
                if not (0 < gap <= c["window_days"]) or not idx.active_on(mk.start):
                    continue
                findings.append(
                    Finding(
                        rule_id=f"prescribing_cascade:{c['id']}",
                        type="prescribing_cascade",
                        severity="warning",
                        title=f"Possible prescribing cascade: {idx.generic} → {c['adverse_effect']} → {mk.generic}",
                        evidence=[med_evidence(idx), med_evidence(mk)],
                        facts={
                            "index_drug": idx.display,
                            "index_brand": idx.brand,
                            "index_class": c["index_label"],
                            "index_start": str(idx.start),
                            "index_source": idx.org,
                            "adverse_effect": c["adverse_effect"],
                            "marker_drug": mk.display,
                            "marker_class": c["marker_label"],
                            "marker_start": str(mk.start),
                            "marker_source": mk.org,
                            "days_between": gap,
                        },
                    )
                )
    return findings
