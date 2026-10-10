"""Record digest for the copilot: compact lines, each with a stable citation key.

Built only from a *scoped* record (consent.get_scoped_record), so the model never sees
anything the viewer can't. Example line:
[Observation/123] 2026-08-05 eGFR 47 mL/min/1.73m² (Medline Path Labs, doc D7 p1)
"""

import re
from dataclasses import dataclass, field
from datetime import date
from typing import Any

from app.models import Alert
from app.services.normalize_dates import pretty_date
from app.services.record import PatientRecord, SourceRef

CITATION_RE = re.compile(
    r"\[((?:Condition|Observation|MedicationRequest|AllergyIntolerance|DocumentReference)/[A-Za-z0-9.\-]+)\]"
)
MAX_CHARS = 600_000  # ≈150k tokens


@dataclass
class Digest:
    text: str
    index: dict[str, dict[str, Any]] = field(default_factory=dict)  # citation key → chip data
    truncated: bool = False

    def known(self, key: str) -> bool:
        return key in self.index


def _src(sources: list[SourceRef]) -> tuple[str, dict[str, Any]]:
    if not sources:
        return "", {}
    s = sources[0]
    extra = f"; also in {', '.join(x.doc_label for x in sources[1:])}" if len(sources) > 1 else ""
    text = f"({s.org or 'unknown source'}, doc {s.doc_label} p{s.page}{extra})"
    return text, {
        "document_id": s.document_id,
        "doc_label": s.doc_label,
        "page": s.page,
        "snippet": s.snippet,
        "org": s.org,
    }


def build_digest(record: PatientRecord, scopes: frozenset[str], alerts: list[Alert], today: date) -> Digest:
    idx: dict[str, dict[str, Any]] = {}
    lines: list[str] = []
    age = today.year - record.dob.year - ((today.month, today.day) < (record.dob.month, record.dob.day))
    lines.append(
        f"PATIENT: {record.display_name}, {record.sex}, {age} years (born {record.dob.isoformat()}), "
        f"blood group {record.blood_group}. Today is {today.isoformat()}. "
        f"Shared sections: {', '.join(sorted(scopes))}."
    )

    if record.allergies:
        lines.append("\nALLERGIES:")
        for a in record.allergies:
            src, chip = _src(a.sources)
            when = (
                f"recorded {a.recorded.year}"
                if a.recorded and a.recorded.month == 1 and a.recorded.day == 1
                else (f"recorded {a.recorded.isoformat()}" if a.recorded else "date unknown")
            )
            lines.append(
                f"[{a.ref}] {a.substance}" + (f" — reaction: {a.reaction}" if a.reaction else "") + f"; {when} {src}"
            )
            idx[a.ref] = {"label": f"{a.substance} allergy", **chip}

    if record.conditions:
        lines.append("\nCONDITIONS:")
        for c in sorted(record.conditions, key=lambda c: c.recorded or date.min):
            src, chip = _src(c.sources)
            code = f" ({c.icd10})" if c.icd10 else ""
            when = f"; recorded {c.recorded.isoformat()}" if c.recorded else ""
            lines.append(f"[{c.ref}] {c.text}{code}, {c.clinical_status}{when} {src}")
            idx[c.ref] = {"label": c.text, **chip}

    if record.medications:
        lines.append("\nMEDICATIONS (all orders, current and past):")
        for m in sorted(record.medications, key=lambda m: m.start or date.min):
            src, chip = _src(m.sources)
            brand = f" (brand {m.brand})" if m.brand else ""
            end = f" until {m.end.isoformat()}" if m.end else ""
            who = f"; prescribed by {m.requester}" if m.requester and not m.sources else ""
            lines.append(
                f"[{m.ref}] {m.display}{brand} {m.frequency_label}"
                + (f" {m.instructions}" if m.instructions else "")
                + f"; started {m.start.isoformat() if m.start else 'unknown'}{end}; status {m.status_on(today)}"
                + f"{who} {src or '(source ' + (m.org or 'unknown') + ')'}"
            )
            idx[m.ref] = {"label": m.display + brand, **chip}

    labs = sorted([o for o in record.observations if o.category == "laboratory"], key=lambda o: o.effective or date.min)
    vitals = sorted(
        [o for o in record.observations if o.category != "laboratory"], key=lambda o: o.effective or date.min
    )
    obs_lines: list[tuple[str, str, dict[str, Any]]] = []
    for o in labs + vitals:
        src, chip = _src(o.sources)
        rng = ""
        if o.ref_low is not None or o.ref_high is not None:
            rng = f" [ref {o.ref_low if o.ref_low is not None else ''}–{o.ref_high if o.ref_high is not None else ''}]"
        flag = {"H": " HIGH", "L": " LOW"}.get(o.interpretation or "", "")
        written = (
            f" (written as {o.written_text})"
            if o.written_text and o.written_text.split(" ")[0] not in o.value_text
            else ""
        )
        when = o.effective.isoformat() if o.effective else "?"
        line = f"[{o.ref}] {when} {o.name} {o.value_text}{flag}{rng}{written} {src}"
        obs_lines.append((o.category, line, {"label": f"{o.name} {o.value_text} ({pretty_date(o.effective)})", **chip}))

    truncated = False
    # Drop the oldest observations first if the digest would be too long.
    while obs_lines and sum(len(x) for x in lines) + sum(len(x[1]) for x in obs_lines) > MAX_CHARS:
        obs_lines.pop(0)
        truncated = True
    if any(cat == "laboratory" for cat, _, _ in obs_lines):
        lines.append("\nLAB RESULTS (oldest first; values in canonical units):")
        lines += [line for cat, line, _ in obs_lines if cat == "laboratory"]
    if any(cat != "laboratory" for cat, _, _ in obs_lines):
        lines.append("\nVITAL SIGNS:")
        lines += [line for cat, line, _ in obs_lines if cat != "laboratory"]
    for _, line, chip in obs_lines:
        key = CITATION_RE.match(line)
        if key:
            idx[key.group(1)] = chip
    if truncated:
        lines.append("\nNOTE: older observations were omitted because the record is very long.")

    listable = record.listable_document_ids
    docs = [
        d
        for d in record.documents
        if d.fhir_ref and (d.id in listable or any(c.get("document_id") == d.id for c in idx.values()))
    ]
    if docs:
        lines.append("\nSOURCE DOCUMENTS:")
        for d in sorted(docs, key=lambda d: d.document_date or ""):
            kind = (d.document_type or "document").replace("_", " ")
            org = d.org or "unknown source"
            lines.append(f"[{d.fhir_ref}] {d.label} {d.document_date or 'undated'} {kind} — {org} ({d.filename})")
            idx[d.fhir_ref or ""] = {
                "label": f"{d.label} {(d.document_type or 'document').replace('_', ' ')}",
                "document_id": d.id,
                "doc_label": d.label,
                "page": 1,
                "snippet": None,
                "org": d.org,
            }

    if alerts:
        lines.append("\nACTIVE SAFETY ALERTS (decided by rules; cite their evidence keys, not the alert):")
        for alert in alerts:
            ev = ", ".join(f"[{e['ref']}]" for e in alert.evidence if e["ref"] in idx)
            lines.append(f"- {alert.severity.upper()} {alert.title}. {alert.clinical_text} Evidence: {ev}")

    return Digest(text="\n".join(lines), index=idx, truncated=truncated)


def extract_citations(text: str, digest: Digest) -> tuple[list[dict[str, Any]], list[str]]:
    """Citation keys used in an answer → (known chips, unknown keys)."""
    seen: list[str] = []
    for m in CITATION_RE.finditer(text):
        if m.group(1) not in seen:
            seen.append(m.group(1))
    known = [{"key": k, **digest.index[k]} for k in seen if digest.known(k)]
    unknown = [k for k in seen if not digest.known(k)]
    return known, unknown
