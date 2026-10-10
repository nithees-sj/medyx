"""The merged clinical record of one health profile, read from HAPI FHIR.

`load_record()` turns FHIR resources (plus document/provenance metadata kept in
Postgres) into plain dataclasses that the safety engine, timeline, trends and copilot
all share. Doctor-facing code must go through `consent.get_scoped_record()` instead.
"""

import asyncio
import uuid
from dataclasses import dataclass, field
from datetime import date
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app import knowledge as kb
from app.models import Document, ExtractionItem, HealthProfile
from app.services import fhir_resources as fr
from app.services.fhir_client import get_fhir


@dataclass
class SourceRef:
    document_id: str
    doc_label: str
    page: int
    snippet: str | None
    org: str | None
    document_date: str | None
    filename: str


@dataclass
class Medication:
    ref: str
    generic: str
    display: str
    brand: str | None
    classes: set[str]
    strength: str | None
    strength_mg: float | None
    frequency_label: str
    frequency_text: str | None
    per_day: float
    as_needed: bool
    instructions: str | None
    start: date | None
    end: date | None
    fhir_status: str
    org: str | None
    requester: str | None
    written_text: str | None
    sources: list[SourceRef] = field(default_factory=list)

    @property
    def psychiatric(self) -> bool:
        return "psychiatric" in self.classes

    def status_on(self, day: date) -> str:
        if self.fhir_status in ("stopped", "cancelled", "entered-in-error"):
            return "stopped"
        if self.end and self.end < day:
            return "completed"
        return "active"

    def active_on(self, day: date) -> bool:
        started = self.start is None or self.start <= day
        return started and self.status_on(day) == "active"


@dataclass
class Observation:
    ref: str
    loinc: str | None
    name: str
    category: str
    value: float | None
    value_text: str
    unit: str | None
    unit_display: str
    decimals: int
    effective: date | None
    interpretation: str | None
    ref_low: float | None
    ref_high: float | None
    org: str | None
    written_text: str | None
    sources: list[SourceRef] = field(default_factory=list)


@dataclass
class Condition:
    ref: str
    text: str
    icd10: str | None
    clinical_status: str
    onset: date | None
    recorded: date | None
    org: str | None
    sources: list[SourceRef] = field(default_factory=list)

    @property
    def mental_health(self) -> bool:
        return bool(self.icd10 and self.icd10.startswith("F"))


@dataclass
class Allergy:
    ref: str
    substance: str
    allergy_class: str | None
    reaction: str | None
    criticality: str | None
    recorded: date | None
    org: str | None
    sources: list[SourceRef] = field(default_factory=list)


@dataclass
class DocumentInfo:
    id: str
    label: str
    seq: int
    fhir_ref: str | None
    filename: str
    mime: str
    page_count: int
    document_type: str | None
    org: str | None
    document_date: str | None
    status: str
    uploader_role: str
    created_at: str
    category: str = "uploaded"


@dataclass
class PatientRecord:
    profile_id: uuid.UUID
    version: int
    patient_ref: str
    display_name: str
    dob: date
    sex: str
    blood_group: str
    conditions: list[Condition] = field(default_factory=list)
    medications: list[Medication] = field(default_factory=list)
    allergies: list[Allergy] = field(default_factory=list)
    observations: list[Observation] = field(default_factory=list)
    documents: list[DocumentInfo] = field(default_factory=list)
    truncated: bool = False
    # Documents shown in the document library (others are only openable as citation sources).
    listable_document_ids: set[str] = field(default_factory=set)

    def series(self, loinc: str) -> list[Observation]:
        return sorted(
            (o for o in self.observations if o.loinc == loinc and o.value is not None and o.effective),
            key=lambda o: o.effective or date.min,
        )

    def labs(self) -> list[Observation]:
        return [o for o in self.observations if o.category == "laboratory"]

    def find(self, ref: str) -> Any:
        for coll in (self.conditions, self.medications, self.allergies, self.observations):
            for x in coll:
                if x.ref == ref:
                    return x
        return None

    def document(self, doc_id: str) -> DocumentInfo | None:
        return next((d for d in self.documents if d.id == doc_id), None)


# ─────────────────────────────── FHIR → dataclasses ───────────────────────────────


def _ext(res: dict[str, Any], url: str) -> list[dict[str, Any]]:
    return [e for e in res.get("extension", []) if e.get("url") == url]


def _ext_str(res: dict[str, Any], url: str) -> str | None:
    e = _ext(res, url)
    return e[0].get("valueString") if e else None


def _org(res: dict[str, Any]) -> str | None:
    e = _ext(res, fr.EXT_SOURCE_ORG)
    return e[0]["valueReference"].get("display") if e else None


def _date(v: str | None) -> date | None:
    if not v:
        return None
    try:
        return date.fromisoformat(v[:10])
    except ValueError:
        return None


def _coding(cc: dict[str, Any] | None, system: str) -> dict[str, Any] | None:
    for c in (cc or {}).get("coding", []):
        if c.get("system") == system:
            return c
    return None


def parse_medication(res: dict[str, Any]) -> Medication:
    mcc = res.get("medicationCodeableConcept", {})
    generic_c = _coding(mcc, fr.GENERIC_SYSTEM)
    generic = generic_c["code"] if generic_c else kb.canonical_generic(mcc.get("text", "unknown"))
    dosage = (res.get("dosageInstruction") or [{}])[0]
    repeat = dosage.get("timing", {}).get("repeat", {})
    bounds = repeat.get("boundsPeriod", {})
    classes = {e["valueCode"] for e in _ext(res, fr.EXT_DRUG_CLASS)}
    from app.services.ingest.normalize import parse_frequency, strength_mg

    freq_text = _ext_str(res, fr.EXT_FREQUENCY_TEXT)
    parsed = parse_frequency(freq_text) if freq_text else None
    display = mcc.get("text") or generic.title()
    strength = _ext_str(res, fr.EXT_STRENGTH)
    from app.services.ingest.normalize import frequency_label

    return Medication(
        ref=f"MedicationRequest/{res['id']}",
        generic=generic,
        display=display,
        brand=_ext_str(res, fr.EXT_BRAND_NAME),
        classes=classes or kb.classes_for(generic),
        strength=strength,
        strength_mg=strength_mg(strength),
        frequency_label=frequency_label(parsed) if parsed else (dosage.get("text") or ""),
        frequency_text=freq_text,
        per_day=float(repeat.get("frequency", 0) or 0),
        as_needed=bool(dosage.get("asNeededBoolean")),
        instructions=(dosage.get("additionalInstruction") or [{}])[0].get("text"),
        start=_date(bounds.get("start") or res.get("authoredOn")),
        end=_date(bounds.get("end")),
        fhir_status=res.get("status", "active"),
        org=_org(res),
        requester=(res.get("requester") or {}).get("display"),
        written_text=_ext_str(res, fr.EXT_WRITTEN_TEXT),
    )


def parse_observation(res: dict[str, Any]) -> Observation:
    code = res.get("code", {})
    loinc_c = _coding(code, fr.LOINC)
    loinc = loinc_c["code"] if loinc_c else None
    category = "laboratory"
    for cat in res.get("category", []):
        for c in cat.get("coding", []):
            if c.get("code") == "vital-signs":
                category = "vital-signs"
    lab = kb.lab_by_code(loinc) if loinc else None
    vq = res.get("valueQuantity")
    rr = (res.get("referenceRange") or [{}])[0]
    interp = (res.get("interpretation") or [{}])[0].get("coding", [{}])[0].get("code")
    if vq:
        number = float(vq["value"])
        value: float | None = number
        unit = vq.get("code") or vq.get("unit")
        unit_display = vq.get("unit") or kb.unit_display(unit)
        decimals = lab.decimals if lab else (0 if number.is_integer() else 1)
        value_text = f"{number:.{decimals}f} {unit_display}".strip()
    else:
        value, unit, unit_display, decimals = None, None, "", 0
        comps = res.get("component", [])
        nums = [str(int(c["valueQuantity"]["value"])) for c in comps if "valueQuantity" in c]
        value_text = ("/".join(nums) + " mmHg") if nums else ""
    if category == "vital-signs" and vq is None and res.get("component"):
        name = "Blood pressure"
    else:
        name = lab.short if lab else (code.get("text") or (loinc_c or {}).get("display") or "Observation")
    return Observation(
        ref=f"Observation/{res['id']}",
        loinc=loinc,
        name=name,
        category=category,
        value=value,
        value_text=value_text,
        unit=unit,
        unit_display=unit_display,
        decimals=decimals,
        effective=_date(res.get("effectiveDateTime")),
        interpretation=interp,
        ref_low=rr.get("low", {}).get("value"),
        ref_high=rr.get("high", {}).get("value"),
        org=_org(res) or ((res.get("performer") or [{}])[0].get("display")),
        written_text=_ext_str(res, fr.EXT_WRITTEN_TEXT),
    )


def parse_condition(res: dict[str, Any]) -> Condition:
    code = res.get("code", {})
    icd = _coding(code, fr.ICD10)
    status = (res.get("clinicalStatus") or {}).get("coding", [{}])[0].get("code", "active")
    return Condition(
        ref=f"Condition/{res['id']}",
        text=code.get("text") or (icd or {}).get("display") or "Condition",
        icd10=icd["code"] if icd else None,
        clinical_status=status,
        onset=_date(res.get("onsetDateTime")),
        recorded=_date(res.get("recordedDate")),
        org=_org(res),
    )


def parse_allergy(res: dict[str, Any]) -> Allergy:
    substance = res.get("code", {}).get("text") or "Unknown substance"
    reaction = None
    for r in res.get("reaction", []):
        for m in r.get("manifestation", []):
            reaction = m.get("text") or reaction
    return Allergy(
        ref=f"AllergyIntolerance/{res['id']}",
        substance=substance,
        allergy_class=kb.allergy_class_for(substance),
        reaction=reaction,
        criticality=res.get("criticality"),
        recorded=_date(res.get("recordedDate")),
        org=_org(res),
    )


# ─────────────────────────────── loading ───────────────────────────────

_cache: dict[uuid.UUID, PatientRecord] = {}


def invalidate(profile_id: uuid.UUID | None = None) -> None:
    if profile_id is None:
        _cache.clear()
    else:
        _cache.pop(profile_id, None)


async def fetch_resources(patient_ref: str) -> dict[str, list[dict[str, Any]]]:
    fhir = get_fhir()
    types = {
        "Condition": {"subject": patient_ref},
        "Observation": {"subject": patient_ref},
        "MedicationRequest": {"subject": patient_ref},
        "AllergyIntolerance": {"patient": patient_ref},
    }
    results = await asyncio.gather(*(fhir.search(t, p) for t, p in types.items()))
    return dict(zip(types, results, strict=True))


async def load_record(db: AsyncSession, profile: HealthProfile) -> PatientRecord:
    cached = _cache.get(profile.id)
    if cached and cached.version == profile.record_version:
        return cached

    patient_ref = f"Patient/{profile.fhir_patient_id}"
    resources = await fetch_resources(patient_ref)

    docs = (await db.scalars(select(Document).where(Document.profile_id == profile.id).order_by(Document.seq))).all()
    doc_by_id = {d.id: d for d in docs}
    items = (
        await db.scalars(
            select(ExtractionItem).where(
                ExtractionItem.document_id.in_(list(doc_by_id)), ExtractionItem.fhir_resource_id.is_not(None)
            )
        )
    ).all()
    sources: dict[str, list[SourceRef]] = {}
    for it in items:
        d = doc_by_id[it.document_id]
        sources.setdefault(it.fhir_resource_id or "", []).append(
            SourceRef(
                document_id=str(d.id),
                doc_label=d.label,
                page=it.page,
                snippet=it.source_snippet,
                org=d.source_org_name,
                document_date=d.document_date.isoformat() if d.document_date else None,
                filename=d.original_filename,
            )
        )

    record = PatientRecord(
        profile_id=profile.id,
        version=profile.record_version,
        patient_ref=patient_ref,
        display_name=profile.display_name,
        dob=profile.dob,
        sex=profile.sex,
        blood_group=profile.blood_group,
        conditions=[parse_condition(r) for r in resources["Condition"]],
        medications=[parse_medication(r) for r in resources["MedicationRequest"]],
        allergies=[parse_allergy(r) for r in resources["AllergyIntolerance"]],
        observations=[parse_observation(r) for r in resources["Observation"]],
        documents=[
            DocumentInfo(
                id=str(d.id),
                label=d.label,
                seq=d.seq,
                fhir_ref=f"DocumentReference/{d.fhir_document_reference_id}" if d.fhir_document_reference_id else None,
                filename=d.original_filename,
                mime=d.mime,
                page_count=d.page_count,
                document_type=d.document_type,
                org=d.source_org_name,
                document_date=d.document_date.isoformat() if d.document_date else None,
                status=d.status,
                uploader_role=d.uploader_role,
                created_at=d.created_at.isoformat(),
                category="clinical_note" if d.document_type == "clinical_note" else "uploaded",
            )
            for d in docs
        ],
    )
    for coll in (record.conditions, record.medications, record.allergies, record.observations):
        for x in coll:
            x.sources = sorted(sources.get(x.ref, []), key=lambda s: (s.document_date or "", s.doc_label))
            if not x.org and x.sources:
                x.org = x.sources[0].org
    _cache[profile.id] = record
    return record
