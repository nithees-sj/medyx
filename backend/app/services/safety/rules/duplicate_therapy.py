"""Two or more active orders for the same molecule, or two drugs from the same listed class."""

from datetime import date
from itertools import combinations

from app.services.record import PatientRecord
from app.services.safety.findings import Finding, med_evidence, molecules

# Classes where taking two different members together is almost always unintended.
DUPLICATE_CLASSES = {
    "ace_inhibitor": "ACE inhibitors",
    "arb": "angiotensin receptor blockers",
    "statin": "statins",
    "ssri": "SSRIs",
    "sulfonylurea": "sulfonylureas",
    "ppi": "proton-pump inhibitors",
    "beta_blocker": "beta-blockers",
    "dihydropyridine_ccb": "calcium-channel blockers",
    "nsaid": "NSAIDs",
    "anticoagulant": "anticoagulants",
}


def evaluate(record: PatientRecord, today: date) -> list[Finding]:
    active = [m for m in record.medications if m.active_on(today)]
    findings: list[Finding] = []
    used: set[frozenset[str]] = set()

    # Same molecule (also inside combination products), grouped per molecule.
    by_molecule: dict[str, list] = {}
    for m in active:
        for mol in molecules(m.generic):
            by_molecule.setdefault(mol, []).append(m)
    for mol, meds in sorted(by_molecule.items()):
        refs = {m.ref for m in meds}
        if len(refs) < 2 or frozenset(refs) in used:
            continue
        used.add(frozenset(refs))
        meds = sorted(meds, key=lambda m: m.start or date.min)
        names = [m.brand or m.display for m in meds]
        findings.append(
            Finding(
                rule_id=f"duplicate_therapy:{mol}",
                type="duplicate_therapy",
                severity="warning",
                title=f"Same medicine prescribed twice: {mol} ({' and '.join(names)})",
                evidence=[med_evidence(m) for m in meds],
                facts={
                    "molecule": mol,
                    "orders": [
                        {
                            "name": m.display,
                            "brand": m.brand,
                            "org": m.org,
                            "start": str(m.start),
                            "frequency": m.frequency_label,
                        }
                        for m in meds
                    ],
                },
            )
        )

    # Different molecules from the same class.
    for cls, label in DUPLICATE_CLASSES.items():
        members = [m for m in active if cls in m.classes]
        for a, b in combinations(members, 2):
            if molecules(a.generic) & molecules(b.generic):
                continue  # already reported as same-molecule
            pair = frozenset({a.ref, b.ref})
            if pair in used:
                continue
            used.add(pair)
            meds = sorted([a, b], key=lambda m: m.start or date.min)
            findings.append(
                Finding(
                    rule_id=f"duplicate_therapy:class:{cls}",
                    type="duplicate_therapy",
                    severity="warning",
                    title=f"Two {label} at the same time: {meds[0].generic} and {meds[1].generic}",
                    evidence=[med_evidence(m) for m in meds],
                    facts={
                        "class": label,
                        "orders": [
                            {"name": m.display, "brand": m.brand, "org": m.org, "start": str(m.start)} for m in meds
                        ],
                    },
                )
            )
    return findings
