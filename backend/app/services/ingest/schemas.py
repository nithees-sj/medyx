"""Structured-output schema for document extraction (spec §7.2).

The model fills this schema; everything after it (codes, units, generics, merging)
is deterministic Python.
"""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

DocType = Literal["prescription", "lab_report", "discharge_summary", "opd_note", "imaging_report", "other"]


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class SourceOrganization(_Strict):
    name: str = Field(description="Hospital, clinic or lab name exactly as printed on the document")
    address: str | None = None


class Practitioner(_Strict):
    name: str | None = Field(default=None, description="Doctor's name as written, e.g. 'Dr. K. Srinivasan'")
    specialty: str | None = None


class DocumentInfo(_Strict):
    type: DocType
    source_organization: SourceOrganization
    practitioner: Practitioner | None = None
    document_date: str | None = Field(
        default=None, description="Visit/report date as ISO YYYY-MM-DD. Indian documents write dates as DD/MM/YYYY."
    )
    encounter_reason: str | None = Field(default=None, description="Chief complaint or reason for the visit")
    patient_name_as_written: str | None = None


class Evidence(_Strict):
    page: int = Field(description="1-based page number where this item appears")
    snippet: str = Field(description="Short verbatim quote from the document that supports this item")
    confidence: float = Field(ge=0, le=1, description="How sure you are this item was read correctly (0-1)")
    uncertain_reason: str | None = Field(
        default=None, description="If anything was hard to read or ambiguous, say what; otherwise null"
    )


class ConditionItem(Evidence):
    text: str = Field(description="Diagnosis as a clinician would name it, e.g. 'Type 2 diabetes mellitus'")
    icd10_guess: str | None = Field(default=None, description="Best ICD-10 code, e.g. E11.9")
    onset_date: str | None = Field(default=None, description="ISO date or year if stated")
    clinical_status: Literal["active", "resolved", "unknown"] = "active"


class FrequencyParsed(_Strict):
    morning: float = 0
    afternoon: float = 0
    night: float = 0
    per_day: float = Field(description="Total doses per day; 0 if only as needed")
    as_needed: bool = Field(default=False, description="True for SOS / PRN")


class MedicationItem(Evidence):
    written_text: str = Field(
        description="The full medicine line verbatim, e.g. 'Tab. Glycomet 500 mg 1-0-1 after food'"
    )
    brand: str | None = Field(default=None, description="Brand name if a brand is written, e.g. 'Glycomet'")
    generic_molecule: str = Field(description="Generic molecule in lowercase English, e.g. 'metformin'")
    strength: str | None = Field(default=None, description="e.g. '500 mg', '10 ml'")
    form: str | None = Field(default=None, description="tablet, capsule, syrup, injection, ...")
    frequency_text: str | None = Field(default=None, description="As written: '1-0-1', 'BD', 'SOS'")
    frequency_parsed: FrequencyParsed
    duration_days: int | None = Field(default=None, description="Course length in days, null if ongoing/continue")
    route: str | None = Field(default="oral")
    start_date: str | None = Field(default=None, description="ISO date the medicine was prescribed")
    instructions: str | None = Field(default=None, description="e.g. 'after food', 'before breakfast'")


class AllergyItem(Evidence):
    substance: str = Field(description="Allergen, e.g. 'Penicillin'")
    reaction: str | None = None
    criticality: Literal["low", "high", "unable-to-assess"] | None = None
    recorded_date: str | None = Field(default=None, description="ISO date or year the allergy was noted")


class LabItem(Evidence):
    test_name_as_written: str
    value: float
    unit_as_written: str | None = None
    reference_range_text: str | None = None
    flag_as_written: str | None = Field(default=None, description="H, L, HIGH, LOW, *, etc. if printed")
    specimen_date: str | None = Field(default=None, description="ISO collection date (or report date if absent)")


class VitalItem(Evidence):
    name: str = Field(description="e.g. 'Blood pressure', 'Pulse', 'Weight', 'BMI', 'Temperature'")
    value: str = Field(description="As written, e.g. '158/96' or '78'")
    unit: str | None = None
    date: str | None = None


class ExtractionResult(_Strict):
    document: DocumentInfo
    conditions: list[ConditionItem] = []
    medications: list[MedicationItem] = []
    allergies: list[AllergyItem] = []
    labs: list[LabItem] = []
    vitals: list[VitalItem] = []
