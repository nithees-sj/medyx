"""Alert explanations. Rules decide that an alert fires; the AI only writes the words.

Every alert gets a deterministic template immediately (so alerts never wait on the AI and
always work offline). A single batched AI call later upgrades them to nicer wording.
"""

import json
import logging
from typing import Any

from pydantic import BaseModel, Field

from app.ai import client as ai
from app.services.normalize_dates import pretty_date as d
from app.services.safety.findings import DISCLAIMER, Finding

log = logging.getLogger(__name__)


class Explanation(BaseModel):
    key: str
    patient_text: str = Field(description="Plain language, 2-3 sentences, ends with the required sentence")
    clinical_text: str = Field(description="Concise clinical summary with dates, sources and values")


class ExplanationBatch(BaseModel):
    items: list[Explanation]


def ensure_disclaimer(text: str) -> str:
    text = text.strip()
    if text.endswith(DISCLAIMER):
        return text
    text = text.replace(DISCLAIMER, "").strip()
    return f"{text} {DISCLAIMER}".strip()


def _orders(orders: list[dict[str, Any]]) -> str:
    return " and ".join(
        f"{o.get('brand') or o.get('name')} from {o.get('org') or 'an unknown source'} ({d(o.get('start'))})"
        for o in orders
    )


def template(f: Finding) -> tuple[str, str]:
    x = f.facts
    if f.type == "duplicate_therapy":
        what = str(x.get("molecule") or x.get("class") or "medicine")
        patient = (
            f"Your records show two prescriptions for {'the same medicine, ' + what if x.get('molecule') else 'two similar ' + what}: "
            f"{_orders(x['orders'])}. Taking both could mean a double dose."
        )
        clinical = (
            f"Duplicate therapy ({what}): "
            + "; ".join(
                f"{o.get('brand') or o.get('name')} {o.get('frequency') or ''} — {o.get('org')}, {d(o.get('start'))}".replace(
                    "  ", " "
                )
                for o in x["orders"]
            )
            + ". Both active; consider reconciling."
        )
    elif f.type == "allergy_conflict":
        med = x["medicine"] + (f" ({x['brand']})" if x.get("brand") else "")
        patient = (
            f"Your record notes a {x['allergy'].lower()} allergy{' (' + x['reaction'] + ')' if x.get('reaction') else ''}, "
            f"but {med} was prescribed on {d(x['medicine_start'])} by {x.get('medicine_source') or 'a clinic'}. "
            f"This medicine belongs to the {x['allergy_class'].lower().removesuffix('s')} family."
        )
        clinical = (
            f"Recorded {x['allergy']} allergy ({x.get('reaction') or 'reaction not stated'}; {x.get('allergy_source')}, "
            f"{d(x.get('allergy_recorded'), 'year' if str(x.get('allergy_recorded') or '').endswith('-01-01') else 'day')}) vs {med} prescribed {d(x['medicine_start'])} at {x.get('medicine_source')} "
            f"({x['allergy_class']} cross-reactivity; order {x.get('medicine_status')})."
        )
    elif f.type == "prescribing_cascade":
        index = x["index_drug"] + (f" ({x['index_brand']})" if x.get("index_brand") else "")
        patient = (
            f"{x['marker_drug']} was started {x['days_between']} days after {index}. "
            f"{x['adverse_effect'].capitalize()} is a known side effect of {x['index_class']} medicines, "
            f"so the newer medicine may be treating a side effect of the older one."
        )
        clinical = (
            f"Possible cascade: {index} ({x['index_class']}, {x.get('index_source')}, {d(x['index_start'])}) → "
            f"{x['adverse_effect']} → {x['marker_drug']} ({x['marker_class']}, {x.get('marker_source')}, "
            f"{d(x['marker_start'])}; {x['days_between']} days later). Index drug still active; consider whether the "
            f"symptom is drug-induced."
        )
    elif f.type == "lab_drift" and x.get("analytes"):
        a = x["analytes"][0]
        trail = " → ".join(v["value"].split(" ")[0] for v in a["values"])
        labs = len({v["lab"] for v in a["values"]})
        friendly = "kidney function test (eGFR)" if a["name"] == "eGFR" else a["name"]
        patient = f"Your {friendly} has moved steadily in one direction across {len(a['values'])} reports from {labs} different labs: {trail}."
        if a.get("all_within_reference_range"):
            patient += " Each result looked acceptable on its own, but together they show a trend."
        if x.get("drug"):
            patient += f" You are taking {x['drug']['name'].split(' ')[0].lower()}, whose dose may need to be reviewed as kidney function changes."
        series = "; ".join(
            f"{an['name']} "
            + " → ".join(f"{v['value']} ({d(v['date'])}, {v['lab']})" for v in an["values"])
            + f" [slope {an['slope_per_year']:+}/yr]"
            for an in x["analytes"]
        )
        clinical = series + "."
        if x.get("projected_cross_date"):
            clinical += f" Projected to reach {x['threshold']} around {d(x['projected_cross_date'], 'month')}."
        if x.get("drug"):
            orders = ", ".join(
                f"{o.get('brand') or 'unbranded'} ({o.get('org')}, {d(o.get('start'))})" for o in x["drug"]["orders"]
            )
            clinical += f" {x['drug']['name']} active: {orders} — consider: {x['drug']['action']}."
    elif f.type == "lab_drift":
        patient = (
            f"Your latest kidney function result is {x['latest']['value']} ({d(x['latest']['date'])}). "
            f"You are taking {x['drug']['name']}, whose dose may need review at this level."
        )
        clinical = f"eGFR {x['latest']['value']} ({x['latest']['lab']}, {d(x['latest']['date'])}) with {x['drug']['name']} active — consider: {x['drug']['action']}."
    else:  # interaction
        patient = f"{x['drug_a']} and {x['drug_b']} are both on your current list. Taken together they can raise the risk of {x['effect']}."
        clinical = f"Interaction: {x['drug_a']} ({x.get('drug_a_source')}) + {x['drug_b']} ({x.get('drug_b_source')}) — risk of {x['effect']}."
    return ensure_disclaimer(patient), clinical.strip()


def apply_templates(findings: list[Finding]) -> None:
    for f in findings:
        f.patient_text, f.clinical_text = template(f)


async def ai_explanations(items: list[dict[str, Any]]) -> dict[str, Explanation]:
    """items: [{key, type, severity, title, facts}] → {key: Explanation}. Raises AIError on failure."""
    batch = await ai.generate_structured(
        purpose="alert_explain",
        system=ai.load_prompt("alert_explanations"),
        contents=[json.dumps({"alerts": items}, default=str, ensure_ascii=False)],
        schema=ExplanationBatch,
        thinking="low",
        temperature=0.2,
        max_quota_wait=60,
    )
    return {e.key: e for e in batch.items}
