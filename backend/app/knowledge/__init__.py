"""Loaders and lookups for the curated knowledge JSON files in this package."""

import functools
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from rapidfuzz import fuzz, process

KNOWLEDGE_DIR = Path(__file__).parent


@functools.cache
def load(name: str) -> dict[str, Any]:
    return json.loads((KNOWLEDGE_DIR / f"{name}.json").read_text(encoding="utf-8"))


def norm_text(s: str) -> str:
    s = s.lower().replace("&", " and ")
    s = re.sub(r"[^a-z0-9+ ]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


# ─────────────────────────────── Labs ───────────────────────────────


@dataclass(frozen=True)
class LabCode:
    code: str
    display: str
    short: str
    unit: str
    decimals: int
    conversions: dict[str, dict[str, float]]

    @property
    def unit_display(self) -> str:
        return unit_display(self.unit)


@functools.cache
def _lab_index() -> tuple[dict[str, LabCode], dict[str, LabCode]]:
    data = load("loinc_map")
    by_alias: dict[str, LabCode] = {}
    by_code: dict[str, LabCode] = {}
    for entry in data["codes"]:
        lc = LabCode(
            code=entry["code"],
            display=entry["display"],
            short=entry["short"],
            unit=entry["unit"],
            decimals=entry["decimals"],
            conversions=entry.get("conversions", {}),
        )
        by_code[lc.code] = lc
        for alias in [*entry["aliases"], entry["short"]]:
            by_alias[norm_text(alias)] = lc
    return by_alias, by_code


def lab_by_code(code: str) -> LabCode | None:
    return _lab_index()[1].get(code)


def match_lab(name: str) -> LabCode | None:
    """Map a lab test name as written to a LOINC entry; None if unknown."""
    by_alias, _ = _lab_index()
    candidates = [name]
    inner = re.findall(r"\(([^)]*)\)", name)
    outer = re.sub(r"\([^)]*\)", " ", name)
    candidates += [outer, *inner]
    for c in candidates:
        hit = by_alias.get(norm_text(c))
        if hit:
            return hit
    # Fuzzy fallback on the whole name; token_sort keeps "urine creatinine" away from "serum creatinine".
    best = process.extractOne(norm_text(name), list(by_alias), scorer=fuzz.token_sort_ratio, score_cutoff=90)
    return by_alias[best[0]] if best else None


def normalize_unit(unit: str | None) -> str | None:
    if not unit:
        return None
    key = unit.strip().lower().replace("µ", "u").replace("μ", "u").replace("²", "2").replace(" ", "")
    key = key.replace("sq.m", "sqm")
    return load("loinc_map")["unit_aliases"].get(key, unit.strip())


def unit_display(ucum: str | None) -> str:
    if not ucum:
        return ""
    return load("loinc_map")["unit_display"].get(ucum, ucum)


@functools.cache
def vital_aliases() -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for v in load("loinc_map")["vitals"]:
        for a in v.get("aliases", []):
            out[a] = v
    return out


def vital_by_key(key: str) -> dict[str, Any]:
    return next(v for v in load("loinc_map")["vitals"] if v["key"] == key)


# ─────────────────────────────── Drugs ──────────────────────────────


@dataclass
class DrugInfo:
    generic: str
    brand: str | None = None
    classes: set[str] = field(default_factory=set)
    known: bool = False


@functools.cache
def _brand_index() -> dict[str, dict[str, Any]]:
    return {norm_text(b["name"]): b for b in load("brand_generic")["brands"]}


def canonical_generic(name: str) -> str:
    """Lowercase generic, synonyms resolved, combination parts normalised and joined with ' + '."""
    data = load("brand_generic")
    syn = data["synonyms"]
    s = re.sub(r"\s+", " ", name.strip().lower())
    if s in syn:
        return syn[s]
    parts = [p.strip() for p in re.split(r"\s*(?:\+|/| and |,)\s*", s) if p.strip()]
    parts = [syn.get(p, p) for p in parts]
    joined = " + ".join(parts)
    return syn.get(joined, joined)


def classes_for(generic: str, strength_mg: float | None = None) -> set[str]:
    data = load("brand_generic")
    generics: dict[str, list[str]] = data["generics"]
    out: set[str] = set()
    for part in generic.split(" + "):
        out.update(generics.get(part, []))
        for rule in data["dose_classes"].get(part, []):
            if strength_mg is not None and strength_mg >= rule["min_mg"]:
                out.add(rule["class"])
    # A brand's listed class (e.g. combination products) also applies.
    for b in load("brand_generic")["brands"]:
        if b["generic"] == generic:
            out.add(b["class"])
            break
    return out


def find_brand(text: str | None) -> dict[str, Any] | None:
    """Find a known brand in a brand field or a written medicine line."""
    if not text:
        return None
    idx = _brand_index()
    t = norm_text(re.sub(r"^(tab|cap|syp|syr|inj|oint|drops?)\.?\s+", "", text.strip(), flags=re.I))
    if t in idx:
        return idx[t]
    # Longest brand name that starts the text, e.g. "dolo 650 sos" → "dolo 650", "glycomet 500 mg" → "glycomet".
    for key in sorted(idx, key=len, reverse=True):
        if t == key or t.startswith(key + " "):
            return idx[key]
    best = process.extractOne(t.split(" ")[0], list(idx), scorer=fuzz.ratio, score_cutoff=90)
    return idx[best[0]] if best else None


def resolve_drug(*, brand: str | None, generic_from_ai: str | None, written_text: str | None) -> DrugInfo:
    """Brand → generic via brand_generic.json, falling back to the AI's generic_molecule."""
    b = find_brand(brand) or find_brand(written_text)
    if b:
        return DrugInfo(generic=b["generic"], brand=b["name"], known=True)
    generic = canonical_generic(generic_from_ai or brand or written_text or "unknown")
    known = all(p in load("brand_generic")["generics"] for p in generic.split(" + "))
    return DrugInfo(generic=generic, brand=brand, known=known)


def drug_catalog() -> list[dict[str, Any]]:
    """Searchable list for the prescribe drawer: brands plus bare generics."""
    data = load("brand_generic")
    items = [
        {
            "label": b["name"],
            "brand": b["name"],
            "generic": b["generic"],
            "form": b["form"],
            "strengths": b["strengths"],
        }
        for b in data["brands"]
    ]
    branded = {b["generic"] for b in data["brands"]}
    items += [
        {"label": g.title(), "brand": None, "generic": g, "form": None, "strengths": []}
        for g in data["generics"]
        if g not in branded
    ]
    return items


# ─────────────────────────────── Allergies ──────────────────────────


@functools.cache
def _allergy_alias_index() -> dict[str, str]:
    out: dict[str, str] = {}
    for key, c in load("allergy_classes")["classes"].items():
        for a in c["aliases"]:
            out[norm_text(a)] = key
    return out


def allergy_class_for(substance: str) -> str | None:
    """'Penicillin' → 'penicillin'; a drug name like 'Amoxicillin' maps to its allergy class too."""
    idx = _allergy_alias_index()
    n = norm_text(substance)
    if n in idx:
        return idx[n]
    generic = canonical_generic(substance)
    classes = classes_for(generic)
    for key, c in load("allergy_classes")["classes"].items():
        if generic in c["members"] or classes & set(c["member_classes"]):
            return key
    return None


def allergy_class(key: str) -> dict[str, Any]:
    return load("allergy_classes")["classes"][key]
