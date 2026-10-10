"""Deterministic normalisation of AI-extracted items: codes, units, generics, dates, status.

Input is one item from ExtractionResult (as a dict); output is a JSON-serialisable dict
stored in extraction_items.payload["normalized"] and used to build FHIR resources.
"""

import re
from datetime import date, timedelta
from typing import Any

from app import knowledge as kb

ICD10_RE = re.compile(r"^[A-TV-Z][0-9][0-9AB](\.[0-9A-TV-Z]{1,4})?$")
_NUM = r"(\d+(?:\.\d+)?)"


# ─────────────────────────────── helpers ───────────────────────────────


def parse_date(value: str | None, fallback: date | None = None) -> date | None:
    """ISO date, or a bare year ("2022") → 1 Jan; otherwise the fallback."""
    if value:
        v = value.strip()
        try:
            return date.fromisoformat(v[:10])
        except ValueError:
            m = re.fullmatch(r"(\d{4})(?:-(\d{2}))?", v)
            if m:
                return date(int(m.group(1)), int(m.group(2) or 1), 1)
    return fallback


def _iso(d: date | None) -> str | None:
    return d.isoformat() if d else None


def strength_mg(strength: str | None) -> float | None:
    if not strength:
        return None
    m = re.search(_NUM + r"\s*(mg|g|mcg|µg|ug)\b", strength.lower())
    if not m:
        return None
    v, u = float(m.group(1)), m.group(2)
    return {"mg": v, "g": v * 1000, "mcg": v / 1000, "µg": v / 1000, "ug": v / 1000}[u]


_FRACTION = {"½": 0.5, "1/2": 0.5, "¼": 0.25, "¾": 0.75}
_ABBREV: dict[str, tuple[float, float, float, float, bool]] = {
    # morning, afternoon, night, per_day, as_needed
    "od": (1, 0, 0, 1, False),
    "qd": (1, 0, 0, 1, False),
    "once daily": (1, 0, 0, 1, False),
    "bd": (1, 0, 1, 2, False),
    "bid": (1, 0, 1, 2, False),
    "twice daily": (1, 0, 1, 2, False),
    "tds": (1, 1, 1, 3, False),
    "tid": (1, 1, 1, 3, False),
    "thrice daily": (1, 1, 1, 3, False),
    "qid": (1, 1, 1, 4, False),
    "hs": (0, 0, 1, 1, False),
    "sos": (0, 0, 0, 0, True),
    "prn": (0, 0, 0, 0, True),
}


def _num(tok: str) -> float:
    return _FRACTION.get(tok) or float(tok)


def parse_frequency(text: str | None) -> dict[str, Any] | None:
    """'1-0-1' → morning 1, night 1, per_day 2. Returns None if not recognised."""
    if not text:
        return None
    t = text.strip().lower()
    dose = r"(\d+(?:\.\d+)?|½|1/2|¼|¾)"
    m = re.search(rf"{dose}\s*[-–—]\s*{dose}\s*[-–—]\s*{dose}", t)
    if m:
        mo, af, ni = (_num(x) for x in m.groups())
        return {"morning": mo, "afternoon": af, "night": ni, "per_day": mo + af + ni, "as_needed": False}
    for key in sorted(_ABBREV, key=len, reverse=True):
        if re.search(rf"\b{re.escape(key)}\b", t):
            mo, af, ni, pd, prn = _ABBREV[key]
            return {"morning": mo, "afternoon": af, "night": ni, "per_day": pd, "as_needed": prn}
    return None


def frequency_label(f: dict[str, Any]) -> str:
    if f.get("as_needed") and not f.get("per_day"):
        return "only when needed (SOS)"

    def fmt(x: float) -> str:
        return "½" if x == 0.5 else str(int(x)) if float(x).is_integer() else str(x)

    return f"{fmt(f['morning'])}-{fmt(f['afternoon'])}-{fmt(f['night'])}"


def parse_reference_range(text: str | None) -> tuple[float | None, float | None]:
    if not text:
        return None, None
    t = text.replace("–", "-").replace("—", "-").replace(",", "")
    m = re.search(_NUM + r"\s*(?:-|to)\s*" + _NUM, t)
    if m:
        return float(m.group(1)), float(m.group(2))
    m = re.search(r"(?:>|≥|>=)\s*" + _NUM, t)
    if m:
        return float(m.group(1)), None
    m = re.search(r"(?:<|≤|<=|upto|up to)\s*" + _NUM, t, flags=re.I)
    if m:
        return None, float(m.group(1))
    return None, None


def _interpretation(flag: str | None, value: float, low: float | None, high: float | None) -> str | None:
    if flag:
        f = flag.strip().lower()
        if f in {"h", "high", "↑", "hi", "*h", "abnormal high"}:
            return "H"
        if f in {"l", "low", "↓", "lo", "*l", "abnormal low"}:
            return "L"
    if high is not None and value > high:
        return "H"
    if low is not None and value < low:
        return "L"
    if low is not None or high is not None:
        return "N"
    return None


# ─────────────────────────────── per type ───────────────────────────────


def normalize_condition(item: dict[str, Any], doc_date: date | None) -> dict[str, Any]:
    code = (item.get("icd10_guess") or "").strip().upper().replace(" ", "") or None
    if code and not ICD10_RE.match(code):
        code = None
    return {
        "text": item["text"].strip(),
        "icd10": code,
        "clinical_status": item.get("clinical_status") or "active",
        "onset_date": _iso(parse_date(item.get("onset_date"))),
        "recorded_date": _iso(doc_date),
        "mental_health": bool(code and code.startswith("F")),
    }


def normalize_medication(item: dict[str, Any], doc_date: date | None, today: date | None = None) -> dict[str, Any]:
    today = today or date.today()
    drug = kb.resolve_drug(
        brand=item.get("brand"), generic_from_ai=item.get("generic_molecule"), written_text=item.get("written_text")
    )
    mg = strength_mg(item.get("strength"))
    classes = sorted(kb.classes_for(drug.generic, mg))
    freq = parse_frequency(item.get("frequency_text"))
    if freq is None:
        fp = item.get("frequency_parsed") or {}
        freq = {
            "morning": fp.get("morning", 0),
            "afternoon": fp.get("afternoon", 0),
            "night": fp.get("night", 0),
            "per_day": fp.get("per_day", 0),
            "as_needed": bool(fp.get("as_needed")),
        }
    start = parse_date(item.get("start_date"), doc_date)
    duration = item.get("duration_days")
    end = start + timedelta(days=int(duration) - 1) if start and duration else None
    status = "completed" if end and end < today else "active"
    strength = (item.get("strength") or "").strip() or None
    form = (item.get("form") or "").strip().lower() or None
    display = " ".join(x for x in [drug.generic.title(), strength, form] if x)
    return {
        "generic": drug.generic,
        "brand": drug.brand or (item.get("brand") or None),
        "known_drug": drug.known,
        "classes": classes,
        "psychiatric": "psychiatric" in classes,
        "display": display,
        "written_text": item.get("written_text"),
        "strength": strength,
        "strength_mg": mg,
        "form": form,
        "frequency_text": item.get("frequency_text"),
        "frequency": freq,
        "frequency_label": frequency_label(freq),
        "duration_days": duration,
        "route": (item.get("route") or "oral").lower(),
        "instructions": item.get("instructions"),
        "start_date": _iso(start),
        "end_date": _iso(end),
        "status": status,
    }


def normalize_allergy(item: dict[str, Any], doc_date: date | None) -> dict[str, Any]:
    substance = item["substance"].strip()
    return {
        "substance": substance,
        "allergy_class": kb.allergy_class_for(substance),
        "reaction": item.get("reaction"),
        "criticality": item.get("criticality"),
        "recorded_date": _iso(parse_date(item.get("recorded_date"), doc_date)),
    }


def normalize_lab(item: dict[str, Any], doc_date: date | None) -> dict[str, Any]:
    name = item["test_name_as_written"].strip()
    value = float(item["value"])
    unit_written = (item.get("unit_as_written") or "").strip() or None
    unit = kb.normalize_unit(unit_written)
    low, high = parse_reference_range(item.get("reference_range_text"))
    lab = kb.match_lab(name)
    converted = False
    out_value, out_unit = value, unit
    if lab:
        if unit is None or unit == lab.unit:
            out_unit = lab.unit
        elif unit in lab.conversions:
            conv = lab.conversions[unit]
            out_value = value * conv["scale"] + conv["offset"]
            low = low * conv["scale"] + conv["offset"] if low is not None else None
            high = high * conv["scale"] + conv["offset"] if high is not None else None
            out_unit = lab.unit
            converted = True
        out_value = round(out_value, lab.decimals)
        low = round(low, lab.decimals + 1) if low is not None else None
        high = round(high, lab.decimals + 1) if high is not None else None
    effective = parse_date(item.get("specimen_date"), doc_date)
    return {
        "test_name_as_written": name,
        "loinc": lab.code if lab else None,
        "loinc_display": lab.display if lab else None,
        "short": lab.short if lab else name,
        "decimals": lab.decimals if lab else 2,
        "value": out_value,
        "unit": out_unit,
        "unit_display": kb.unit_display(out_unit),
        "value_as_written": f"{item['value']:g} {unit_written or ''}".strip(),
        "unit_as_written": unit_written,
        "converted": converted,
        "unit_unrecognized": bool(lab and unit and unit != lab.unit and not converted),
        "reference_low": low,
        "reference_high": high,
        "reference_text": item.get("reference_range_text"),
        "interpretation": _interpretation(item.get("flag_as_written"), out_value, low, high),
        "effective_date": _iso(effective),
    }


def normalize_vital(item: dict[str, Any], doc_date: date | None) -> dict[str, Any] | None:
    name = item["name"].strip().lower()
    spec = kb.vital_aliases().get(name)
    if spec is None:
        for alias, v in kb.vital_aliases().items():
            if alias in name:
                spec = v
                break
    if spec is None:
        return None
    raw = str(item["value"]).strip()
    effective = _iso(parse_date(item.get("date"), doc_date))
    if spec["key"] == "bp":
        m = re.search(r"(\d{2,3})\s*/\s*(\d{2,3})", raw)
        if not m:
            return None
        return {
            "key": "bp",
            "loinc": spec["code"],
            "display": spec["display"],
            "systolic": float(m.group(1)),
            "diastolic": float(m.group(2)),
            "unit": "mm[Hg]",
            "value_text": f"{m.group(1)}/{m.group(2)} mmHg",
            "effective_date": effective,
        }
    m = re.search(_NUM, raw)
    if not m:
        return None
    unit = kb.normalize_unit(item.get("unit")) or spec["unit"]
    return {
        "key": spec["key"],
        "loinc": spec["code"],
        "display": spec["display"],
        "value": float(m.group(1)),
        "unit": unit,
        "value_text": f"{m.group(1)} {kb.unit_display(unit)}".strip(),
        "effective_date": effective,
    }


NORMALIZERS = {
    "Condition": normalize_condition,
    "MedicationRequest": normalize_medication,
    "AllergyIntolerance": normalize_allergy,
    "Observation": normalize_lab,
    "Vital": normalize_vital,
}
