"""Silent lab drift across labs, plus drug–lab combinations (metformin with falling eGFR).

Needs >= min_points results spanning >= min_span_days. A linear regression (numpy.polyfit)
of value vs time fires when the slope moves in the bad direction faster than the rule's
minimum, even if every value is still inside the reference range. Rules in the same group
(e.g. eGFR + creatinine = "kidney") produce one alert.
"""

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any

import numpy as np

from app import knowledge as kb
from app.services.record import Medication, Observation, PatientRecord
from app.services.safety.findings import Finding, med_evidence, molecules, obs_evidence

DAYS_PER_YEAR = 365.25


@dataclass
class Fit:
    rule: dict[str, Any]
    points: list[Observation]
    slope_per_year: float
    intercept: float  # value at t0
    t0: date
    fires: bool

    def value_on(self, d: date) -> float:
        return self.intercept + self.slope_per_year * ((d - self.t0).days / DAYS_PER_YEAR)

    def cross_date(self) -> date | None:
        """When the fitted line reaches the rule threshold (None if moving away from it)."""
        if self.slope_per_year == 0:
            return None
        years = (self.rule["threshold"] - self.intercept) / self.slope_per_year
        if years < 0:
            return None
        return self.t0 + timedelta(days=round(years * DAYS_PER_YEAR))

    def chart(self, horizon_days: int = 365) -> dict[str, Any]:
        first = self.points[0].effective or self.t0
        last = self.points[-1].effective or self.t0
        cross = self.cross_date()
        end = cross if cross and cross > last else last + timedelta(days=horizon_days // 2)
        end = min(end, last + timedelta(days=horizon_days))
        decimals = 2 if abs(self.slope_per_year) < 1 else 1
        return {
            "loinc": self.rule["loinc"],
            "name": self.rule["name"],
            "slope_per_year": round(self.slope_per_year, 3),
            "fitted": [
                {"date": first.isoformat(), "value": round(self.value_on(first), decimals)},
                {"date": last.isoformat(), "value": round(self.value_on(last), decimals)},
            ],
            "projection": [
                {"date": last.isoformat(), "value": round(self.value_on(last), decimals)},
                {"date": end.isoformat(), "value": round(self.value_on(end), decimals)},
            ],
            "threshold": self.rule["threshold"],
            "threshold_label": self.rule["threshold_label"],
            "projected_cross_date": cross.isoformat() if cross else None,
            "fires": self.fires,
        }


def fit_series(rule: dict[str, Any], series: list[Observation], min_points: int, min_span_days: int) -> Fit | None:
    pts = [o for o in series if o.value is not None and o.effective]
    if len(pts) < min_points:
        return None
    t0 = pts[0].effective
    assert t0 is not None
    if ((pts[-1].effective or t0) - t0).days < min_span_days:
        return None
    t = np.array([((o.effective or t0) - t0).days / DAYS_PER_YEAR for o in pts])
    v = np.array([o.value for o in pts], dtype=float)
    slope, intercept = np.polyfit(t, v, 1)
    bad_down = rule["bad_direction"] == "down" and slope <= -rule["min_slope_per_year"]
    bad_up = rule["bad_direction"] == "up" and slope >= rule["min_slope_per_year"]
    return Fit(rule, pts, float(slope), float(intercept), t0, bool(bad_down or bad_up))


def _metformin(record: PatientRecord, today: date, mols: list[str]) -> list[Medication]:
    return [m for m in record.medications if m.active_on(today) and molecules(m.generic) & set(mols)]


def evaluate(record: PatientRecord, today: date) -> list[Finding]:
    cfg = kb.load("drift_rules")
    findings: list[Finding] = []
    groups: dict[str, list[Fit]] = {}
    for rule in cfg["rules"]:
        f = fit_series(rule, record.series(rule["loinc"]), cfg["min_points"], cfg["min_span_days"])
        if f:
            groups.setdefault(rule["group"], []).append(f)

    handled_drug_lab: set[str] = set()
    for group, fits in groups.items():
        firing = [f for f in fits if f.fires]
        if not firing:
            continue
        primary = next((f for f in firing if f.rule.get("primary")), firing[0])
        cross = primary.cross_date()
        latest = primary.points[-1]
        evidence = [obs_evidence(o) for f in firing for o in f.points]
        severity = "warning"
        drug_lab = None
        for dl in cfg["drug_lab"]:
            if dl["group"] != group:
                continue
            meds = _metformin(record, today, dl["molecules"])
            egfr = record.series(dl["loinc"])
            latest_egfr = egfr[-1].value if egfr else None
            soon = (
                cross is not None
                and primary.rule["loinc"] == dl["loinc"]
                and cross <= today + timedelta(days=30 * dl["projection_months"])
            )
            if meds and latest_egfr is not None and (latest_egfr < dl["review_below"] or soon):
                drug_lab = {"rule": dl, "meds": meds, "latest_egfr": latest_egfr}
                evidence += [med_evidence(m) for m in meds]
                if latest_egfr < dl["critical_below"]:
                    severity = "critical"
                handled_drug_lab.add(dl["id"])
        direction = "declining" if primary.slope_per_year < 0 else "rising"
        names = " and ".join(sorted({f.rule["name"] for f in firing}))
        if drug_lab:
            drug, action = drug_lab["meds"][0].generic, drug_lab["rule"]["action"]
            title = f"Kidney function {direction} across labs while on {drug} — {action}"
        else:
            title = f"{names} steadily {direction} across labs"
        findings.append(
            Finding(
                rule_id=f"lab_drift:{group}" + (":metformin" if drug_lab else ""),
                type="lab_drift",
                severity=severity,
                title=title,
                evidence=evidence,
                facts={
                    "analytes": [
                        {
                            "name": f.rule["name"],
                            "values": [
                                {
                                    "date": str(o.effective),
                                    "value": o.value_text,
                                    "lab": o.org,
                                    "as_written": o.written_text,
                                }
                                for o in f.points
                            ],
                            "slope_per_year": round(f.slope_per_year, 2),
                            "all_within_reference_range": all(
                                (o.ref_low is None or (o.value or 0) >= o.ref_low)
                                and (o.ref_high is None or (o.value or 0) <= o.ref_high)
                                for o in f.points
                            ),
                        }
                        for f in firing
                    ],
                    "threshold": primary.rule["threshold_label"],
                    "projected_cross_date": cross.isoformat() if cross else None,
                    "latest": {"date": str(latest.effective), "value": latest.value_text, "lab": latest.org},
                    "today": today.isoformat(),
                    "drug": {
                        "name": drug_lab["meds"][0].display,
                        "orders": [{"brand": m.brand, "org": m.org, "start": str(m.start)} for m in drug_lab["meds"]],
                        "action": drug_lab["rule"]["action"],
                    }
                    if drug_lab
                    else None,
                },
                details={
                    "series": {
                        f.rule["loinc"]: {**f.chart(), "cross_passed": bool((c := f.cross_date()) and c < today)}
                        for f in firing
                    }
                },
            )
        )

    # Drug–lab rule on its own (no drift, but already below the threshold).
    for dl in cfg["drug_lab"]:
        if dl["id"] in handled_drug_lab:
            continue
        meds = _metformin(record, today, dl["molecules"])
        egfr = record.series(dl["loinc"])
        if not meds or not egfr or (egfr[-1].value or 99) >= dl["review_below"]:
            continue
        latest = egfr[-1]
        findings.append(
            Finding(
                rule_id=f"lab_drift:{dl['id']}",
                type="lab_drift",
                severity="critical" if (latest.value or 99) < dl["critical_below"] else "warning",
                title=f"eGFR {latest.value_text} while on {meds[0].generic} — {dl['action']}",
                evidence=[obs_evidence(latest), *(med_evidence(m) for m in meds)],
                facts={
                    "latest": {"date": str(latest.effective), "value": latest.value_text, "lab": latest.org},
                    "drug": {"name": meds[0].display, "action": dl["action"]},
                },
            )
        )
    return findings
