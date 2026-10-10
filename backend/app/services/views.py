"""Shapes the record into what the timeline, trends and medication screens need."""

from datetime import date
from typing import Any

from app import knowledge as kb
from app.services.record import Medication, Observation, PatientRecord, SourceRef

# Categorical hues for source organisations, in fixed order. They avoid the reserved status colours
# (red/amber/green) and the teal brand, and pass the dataviz palette validator (lightness band, chroma
# floor, adjacent-pair CVD ΔE >= 8, normal-vision floor, 3:1 contrast on the light surface).
ORG_PALETTE = ["#2563eb", "#db2777", "#0891b2", "#4a3aa7", "#c026d3", "#9d174d", "#7c3aed", "#be185d"]


def org_colors(record: PatientRecord) -> dict[str, str]:
    """Stable per-profile colour per source organisation, by first appearance in time."""
    seen: list[str] = []
    for d in sorted(record.documents, key=lambda d: (d.document_date or "9999", d.seq)):
        if d.org and d.org not in seen:
            seen.append(d.org)
    for coll in (record.medications, record.conditions, record.observations, record.allergies):
        for x in coll:
            if x.org and x.org not in seen:
                seen.append(x.org)
    return {name: ORG_PALETTE[i % len(ORG_PALETTE)] for i, name in enumerate(seen)}


def source_json(s: SourceRef) -> dict[str, Any]:
    return {
        "document_id": s.document_id,
        "doc_label": s.doc_label,
        "page": s.page,
        "snippet": s.snippet,
        "org": s.org,
        "document_date": s.document_date,
        "filename": s.filename,
    }


def medication_json(m: Medication, today: date) -> dict[str, Any]:
    return {
        "ref": m.ref,
        "generic": m.generic,
        "display": m.display,
        "brand": m.brand,
        "classes": sorted(m.classes),
        "strength": m.strength,
        "frequency_label": m.frequency_label,
        "frequency_text": m.frequency_text,
        "as_needed": m.as_needed,
        "instructions": m.instructions,
        "start": m.start.isoformat() if m.start else None,
        "end": m.end.isoformat() if m.end else None,
        "status": m.status_on(today),
        "org": m.org,
        "requester": m.requester,
        "written_text": m.written_text,
        "sources": [source_json(s) for s in m.sources],
    }


def observation_json(o: Observation) -> dict[str, Any]:
    return {
        "ref": o.ref,
        "loinc": o.loinc,
        "name": o.name,
        "category": o.category,
        "value": o.value,
        "value_text": o.value_text,
        "unit": o.unit,
        "unit_display": o.unit_display,
        "date": o.effective.isoformat() if o.effective else None,
        "interpretation": o.interpretation,
        "ref_low": o.ref_low,
        "ref_high": o.ref_high,
        "org": o.org,
        "written_text": o.written_text,
        "sources": [source_json(s) for s in o.sources],
    }


def timeline(record: PatientRecord, today: date) -> dict[str, Any]:
    items: list[dict[str, Any]] = []
    for c in record.conditions:
        start = (
            c.onset
            or c.recorded
            or (date.fromisoformat(c.sources[0].document_date) if c.sources and c.sources[0].document_date else None)
        )
        if not start:
            continue
        items.append(
            {
                "id": c.ref,
                "group": "conditions",
                "kind": "point",
                "title": c.text,
                "subtitle": c.icd10,
                "start": start.isoformat(),
                "org": c.org,
                "status": c.clinical_status,
                "sources": [source_json(s) for s in c.sources],
            }
        )
    for m in record.medications:
        if not m.start:
            continue
        status = m.status_on(today)
        end = m.end or (today if status == "active" else m.start)
        items.append(
            {
                "id": m.ref,
                "group": "medications",
                "kind": "range",
                "title": m.display + (f" ({m.brand})" if m.brand else ""),
                "subtitle": m.frequency_label,
                "start": m.start.isoformat(),
                "end": end.isoformat(),
                "ongoing": status == "active" and m.end is None,
                "org": m.org,
                "status": status,
                "sources": [source_json(s) for s in m.sources],
            }
        )
    for o in record.labs():  # vital signs stay out of the timeline (they'd crowd the labs lane)
        if not o.effective:
            continue
        items.append(
            {
                "id": o.ref,
                "group": "labs",
                "kind": "point",
                "title": f"{o.name} {o.value_text}".strip(),
                "subtitle": {"H": "above range", "L": "below range"}.get(o.interpretation or ""),
                "start": o.effective.isoformat(),
                "org": o.org,
                "status": o.interpretation,
                "sources": [source_json(s) for s in o.sources],
            }
        )
    for d in record.documents:
        if not d.document_date:
            continue
        items.append(
            {
                "id": f"doc:{d.id}",
                "group": "documents",
                "kind": "point",
                "title": f"{d.label} · {(d.document_type or 'document').replace('_', ' ')}",
                "subtitle": d.filename,
                "start": d.document_date,
                "org": d.org,
                "status": d.status,
                "document_id": d.id,
                "sources": [],
            }
        )
    groups = [
        {"id": "conditions", "label": "Conditions"},
        {"id": "medications", "label": "Medications"},
        {"id": "labs", "label": "Labs"},
        {"id": "documents", "label": "Documents"},
    ]
    return {"groups": groups, "items": items, "org_colors": org_colors(record)}


def trends(record: PatientRecord) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    by_code: dict[str, list[Observation]] = {}
    for o in record.labs():
        if o.loinc and o.value is not None and o.effective:
            by_code.setdefault(o.loinc, []).append(o)
    for code, obs in by_code.items():
        obs.sort(key=lambda o: o.effective or date.min)
        lab = kb.lab_by_code(code)
        lows = [o.ref_low for o in obs if o.ref_low is not None]
        highs = [o.ref_high for o in obs if o.ref_high is not None]
        out.append(
            {
                "loinc": code,
                "name": lab.short if lab else obs[0].name,
                "display": lab.display if lab else obs[0].name,
                "unit": obs[0].unit_display,
                "decimals": lab.decimals if lab else 2,
                "ref_low": max(set(lows), key=lows.count) if lows else None,
                "ref_high": max(set(highs), key=highs.count) if highs else None,
                "count": len(obs),
                "points": [observation_json(o) for o in obs],
                "latest": observation_json(obs[-1]),
                "drift": None,
            }
        )
    out.sort(key=lambda t: (-t["count"], t["name"]))
    return out
