"""Builders for the FHIR R4 resources HealthThread writes, validated with fhir.resources (R4B)."""

from datetime import date
from typing import Any

from fhir.resources.R4B import get_fhir_model_class

EXT_BASE = "https://healththread.app/fhir/StructureDefinition"
EXT_SOURCE_PAGE = f"{EXT_BASE}/source-page"
EXT_BRAND_NAME = f"{EXT_BASE}/brand-name"
EXT_CONFIDENCE = f"{EXT_BASE}/extraction-confidence"
EXT_WRITTEN_TEXT = f"{EXT_BASE}/written-text"
EXT_BLOOD_GROUP = f"{EXT_BASE}/blood-group"
EXT_DRUG_CLASS = f"{EXT_BASE}/drug-class"
EXT_FREQUENCY_TEXT = f"{EXT_BASE}/frequency-text"
EXT_STRENGTH = f"{EXT_BASE}/strength"

HT_ID_SYSTEM = "https://healththread.app/fhir/healththread-id"
HT_TAG_SYSTEM = "https://healththread.app/fhir/tag"


class FhirValidationError(ValueError):
    pass


def validate(resource: dict[str, Any]) -> dict[str, Any]:
    """Validate a resource dict against the R4B model; returns it unchanged if valid."""
    try:
        get_fhir_model_class(resource["resourceType"]).model_validate(resource)
    except Exception as e:  # pydantic.ValidationError, KeyError
        raise FhirValidationError(f"{resource.get('resourceType')}: {e}") from e
    return resource


def _split_name(full_name: str) -> dict[str, Any]:
    parts = full_name.strip().split()
    if len(parts) == 1:
        return {"text": full_name, "given": parts}
    return {"text": full_name, "given": parts[:-1], "family": parts[-1]}


def patient(
    *,
    name: str,
    dob: date,
    sex: str,
    blood_group: str,
    healththread_id: str,
    emergency_contact_name: str | None,
    emergency_contact_phone: str | None,
) -> dict[str, Any]:
    res: dict[str, Any] = {
        "resourceType": "Patient",
        "identifier": [{"system": HT_ID_SYSTEM, "value": healththread_id}],
        "name": [_split_name(name)],
        "gender": sex if sex in ("male", "female", "other") else "unknown",
        "birthDate": dob.isoformat(),
        "extension": [{"url": EXT_BLOOD_GROUP, "valueString": blood_group}],
    }
    if emergency_contact_name:
        contact: dict[str, Any] = {
            "relationship": [
                {
                    "coding": [
                        {
                            "system": "http://terminology.hl7.org/CodeSystem/v2-0131",
                            "code": "C",
                            "display": "Emergency Contact",
                        }
                    ]
                }
            ],
            "name": {"text": emergency_contact_name},
        }
        if emergency_contact_phone:
            contact["telecom"] = [{"system": "phone", "value": emergency_contact_phone}]
        res["contact"] = [contact]
    return validate(res)


def practitioner(
    *, full_name: str, specialty: str, council: str, registration_number: str, organization: str
) -> dict[str, Any]:
    name = full_name.removeprefix("Dr.").removeprefix("Dr ").strip()
    hn = _split_name(name)
    hn["prefix"] = ["Dr."]
    hn["text"] = f"Dr. {name}"
    res = {
        "resourceType": "Practitioner",
        "active": True,
        "identifier": [
            {
                "system": "https://healththread.app/fhir/medical-council-registration",
                "value": registration_number,
                "assigner": {"display": council},
            }
        ],
        "name": [hn],
        "qualification": [{"code": {"text": specialty}, "issuer": {"display": organization}}],
    }
    return validate(res)


# ─────────────────────────────── Clinical resources from documents ───────────────────────────────

EXT_SOURCE_SNIPPET = f"{EXT_BASE}/source-snippet"
EXT_SOURCE_ORG = f"{EXT_BASE}/source-organization"
DOC_ID_SYSTEM = "https://healththread.app/fhir/document-id"
DOC_CATEGORY_SYSTEM = "https://healththread.app/fhir/CodeSystem/document-category"
GENERIC_SYSTEM = "https://healththread.app/fhir/CodeSystem/generic-drug"
LOINC = "http://loinc.org"
ICD10 = "http://hl7.org/fhir/sid/icd-10"
UCUM = "http://unitsofmeasure.org"

DOC_TYPE_LABELS = {
    "prescription": "Prescription",
    "lab_report": "Laboratory report",
    "discharge_summary": "Discharge summary",
    "opd_note": "Outpatient consultation note",
    "imaging_report": "Imaging report",
    "other": "Medical document",
    "clinical_note": "Clinical note",
}


def ref(reference: str, display: str | None = None) -> dict[str, Any]:
    r: dict[str, Any] = {"reference": reference}
    if display:
        r["display"] = display
    return r


def _ext_string(url: str, value: str | None) -> list[dict[str, Any]]:
    return [{"url": url, "valueString": value}] if value else []


def _ext_confidence(value: float | None) -> list[dict[str, Any]]:
    return [{"url": EXT_CONFIDENCE, "valueDecimal": round(value, 3)}] if value is not None else []


def _ext_org(org: dict[str, Any] | None) -> list[dict[str, Any]]:
    return [{"url": EXT_SOURCE_ORG, "valueReference": org}] if org else []


def organization(name: str, address: str | None = None) -> dict[str, Any]:
    res: dict[str, Any] = {"resourceType": "Organization", "active": True, "name": name}
    if address:
        res["address"] = [{"text": address}]
    return validate(res)


def document_practitioner(name: str, specialty: str | None) -> dict[str, Any]:
    res: dict[str, Any] = {"resourceType": "Practitioner", "name": [{"text": name}]}
    if specialty:
        res["qualification"] = [{"code": {"text": specialty}}]
    return validate(res)


def document_reference(
    *,
    patient_ref: str,
    doc_id: str,
    doc_type: str,
    title: str,
    content_type: str,
    url: str,
    size: int,
    sha1_b64: str,
    created_instant: str,
    document_date: str | None,
    author: dict[str, Any] | None,
    category: str = "uploaded",
    data_b64: str | None = None,
) -> dict[str, Any]:
    attachment: dict[str, Any] = {"contentType": content_type, "title": title, "size": size, "hash": sha1_b64}
    if data_b64 is not None:
        attachment["data"] = data_b64
    else:
        attachment["url"] = url
    if document_date:
        attachment["creation"] = document_date
    res: dict[str, Any] = {
        "resourceType": "DocumentReference",
        "status": "current",
        "identifier": [{"system": DOC_ID_SYSTEM, "value": doc_id}],
        "type": {"text": DOC_TYPE_LABELS.get(doc_type, "Medical document")},
        "category": [{"coding": [{"system": DOC_CATEGORY_SYSTEM, "code": category}]}],
        "subject": ref(patient_ref),
        "date": created_instant,
        "description": title,
        "content": [{"attachment": attachment}],
    }
    if author:
        res["author"] = [author]
    if document_date:
        res["context"] = {"period": {"start": document_date}}
    return validate(res)


def encounter(
    *,
    patient_ref: str,
    date: str | None,
    org: dict[str, Any] | None,
    practitioner: dict[str, Any] | None,
    reason: str | None,
) -> dict[str, Any]:
    res: dict[str, Any] = {
        "resourceType": "Encounter",
        "status": "finished",
        "class": {"system": "http://terminology.hl7.org/CodeSystem/v3-ActCode", "code": "AMB", "display": "ambulatory"},
        "subject": ref(patient_ref),
    }
    if date:
        res["period"] = {"start": date}
    if org:
        res["serviceProvider"] = org
    if practitioner:
        res["participant"] = [{"individual": practitioner}]
    if reason:
        res["reasonCode"] = [{"text": reason}]
    return validate(res)


def condition(n: dict[str, Any], *, patient_ref: str, encounter_ref: str | None, org: dict | None, item: dict) -> dict:
    code: dict[str, Any] = {"text": n["text"]}
    if n.get("icd10"):
        code["coding"] = [{"system": ICD10, "code": n["icd10"], "display": n["text"]}]
    status = n.get("clinical_status") if n.get("clinical_status") in ("active", "resolved") else "active"
    res: dict[str, Any] = {
        "resourceType": "Condition",
        "clinicalStatus": {
            "coding": [{"system": "http://terminology.hl7.org/CodeSystem/condition-clinical", "code": status}]
        },
        "verificationStatus": {
            "coding": [{"system": "http://terminology.hl7.org/CodeSystem/condition-ver-status", "code": "confirmed"}]
        },
        "category": [
            {
                "coding": [
                    {
                        "system": "http://terminology.hl7.org/CodeSystem/condition-category",
                        "code": "encounter-diagnosis",
                    }
                ]
            }
        ],
        "code": code,
        "subject": ref(patient_ref),
        "extension": _ext_confidence(item.get("confidence")) + _ext_org(org),
    }
    if encounter_ref:
        res["encounter"] = ref(encounter_ref)
    if n.get("onset_date"):
        res["onsetDateTime"] = n["onset_date"]
    if n.get("recorded_date"):
        res["recordedDate"] = n["recorded_date"]
    return validate(res)


def _quantity(value: float, unit: str | None, unit_display: str | None) -> dict[str, Any]:
    q: dict[str, Any] = {"value": value}
    if unit:
        q["unit"] = unit_display or unit
        if not any(c.isspace() for c in unit):
            q["system"] = UCUM
            q["code"] = unit
    return q


def lab_observation(n: dict[str, Any], *, patient_ref: str, org: dict | None, item: dict) -> dict[str, Any]:
    code: dict[str, Any] = {"text": n["test_name_as_written"]}
    if n.get("loinc"):
        code["coding"] = [{"system": LOINC, "code": n["loinc"], "display": n["loinc_display"]}]
    res: dict[str, Any] = {
        "resourceType": "Observation",
        "status": "final",
        "category": [
            {
                "coding": [
                    {
                        "system": "http://terminology.hl7.org/CodeSystem/observation-category",
                        "code": "laboratory",
                        "display": "Laboratory",
                    }
                ]
            }
        ],
        "code": code,
        "subject": ref(patient_ref),
        "valueQuantity": _quantity(n["value"], n.get("unit"), n.get("unit_display")),
        "extension": _ext_string(EXT_WRITTEN_TEXT, n.get("value_as_written"))
        + _ext_confidence(item.get("confidence"))
        + _ext_org(org),
    }
    if n.get("effective_date"):
        res["effectiveDateTime"] = n["effective_date"]
    if org:
        res["performer"] = [org]
    if n.get("interpretation"):
        res["interpretation"] = [
            {
                "coding": [
                    {
                        "system": "http://terminology.hl7.org/CodeSystem/v3-ObservationInterpretation",
                        "code": n["interpretation"],
                    }
                ]
            }
        ]
    rr: dict[str, Any] = {}
    if n.get("reference_low") is not None:
        rr["low"] = _quantity(n["reference_low"], n.get("unit"), n.get("unit_display"))
    if n.get("reference_high") is not None:
        rr["high"] = _quantity(n["reference_high"], n.get("unit"), n.get("unit_display"))
    if n.get("reference_text"):
        rr["text"] = n["reference_text"]
    if rr:
        res["referenceRange"] = [rr]
    return validate(res)


def vital_observation(
    n: dict[str, Any], *, patient_ref: str, encounter_ref: str | None, org: dict | None, item: dict
) -> dict:
    res: dict[str, Any] = {
        "resourceType": "Observation",
        "status": "final",
        "category": [
            {
                "coding": [
                    {
                        "system": "http://terminology.hl7.org/CodeSystem/observation-category",
                        "code": "vital-signs",
                        "display": "Vital Signs",
                    }
                ]
            }
        ],
        "code": {"coding": [{"system": LOINC, "code": n["loinc"], "display": n["display"]}], "text": n["display"]},
        "subject": ref(patient_ref),
        "extension": _ext_string(EXT_WRITTEN_TEXT, n.get("value_text"))
        + _ext_confidence(item.get("confidence"))
        + _ext_org(org),
    }
    if encounter_ref:
        res["encounter"] = ref(encounter_ref)
    if n.get("effective_date"):
        res["effectiveDateTime"] = n["effective_date"]
    if n["key"] == "bp":
        mmhg = {"unit": "mmHg", "system": UCUM, "code": "mm[Hg]"}
        res["component"] = [
            {
                "code": {"coding": [{"system": LOINC, "code": "8480-6", "display": "Systolic blood pressure"}]},
                "valueQuantity": {"value": n["systolic"], **mmhg},
            },
            {
                "code": {"coding": [{"system": LOINC, "code": "8462-4", "display": "Diastolic blood pressure"}]},
                "valueQuantity": {"value": n["diastolic"], **mmhg},
            },
        ]
    else:
        from app import knowledge as kb

        res["valueQuantity"] = _quantity(n["value"], n["unit"], kb.unit_display(n["unit"]))
    return validate(res)


def medication_request(
    n: dict[str, Any],
    *,
    patient_ref: str,
    encounter_ref: str | None,
    requester: dict | None,
    org: dict | None,
    item: dict,
    note: str | None = None,
) -> dict[str, Any]:
    f = n["frequency"]
    repeat: dict[str, Any] = {}
    if f.get("per_day"):
        repeat.update({"frequency": max(1, round(f["per_day"])), "period": 1, "periodUnit": "d"})
    if n.get("start_date"):
        repeat["boundsPeriod"] = {"start": n["start_date"], **({"end": n["end_date"]} if n.get("end_date") else {})}
    dosage: dict[str, Any] = {
        "text": " ".join(x for x in [n.get("frequency_text") or n["frequency_label"], n.get("instructions")] if x),
        "asNeededBoolean": bool(f.get("as_needed")),
        "route": {"text": n.get("route") or "oral"},
    }
    if repeat:
        dosage["timing"] = {"repeat": repeat}
    if n.get("instructions"):
        dosage["additionalInstruction"] = [{"text": n["instructions"]}]
    ext = (
        _ext_string(EXT_BRAND_NAME, n.get("brand"))
        + _ext_string(EXT_WRITTEN_TEXT, n.get("written_text"))
        + _ext_string(EXT_FREQUENCY_TEXT, n.get("frequency_text"))
        + _ext_string(EXT_STRENGTH, n.get("strength"))
        + _ext_confidence(item.get("confidence"))
        + [{"url": EXT_DRUG_CLASS, "valueCode": c} for c in n.get("classes", [])]
        + _ext_org(org)
    )
    res: dict[str, Any] = {
        "resourceType": "MedicationRequest",
        "status": n["status"],
        "intent": "order",
        "medicationCodeableConcept": {
            "coding": [{"system": GENERIC_SYSTEM, "code": n["generic"], "display": n["generic"].title()}],
            "text": n["display"],
        },
        "subject": ref(patient_ref),
        "dosageInstruction": [dosage],
        "extension": ext,
    }
    if encounter_ref:
        res["encounter"] = ref(encounter_ref)
    if n.get("start_date"):
        res["authoredOn"] = n["start_date"]
    if requester:
        res["requester"] = requester
    if note:
        res["note"] = [{"text": note}]
    return validate(res)


def allergy_intolerance(n: dict[str, Any], *, patient_ref: str, org: dict | None, item: dict) -> dict[str, Any]:
    res: dict[str, Any] = {
        "resourceType": "AllergyIntolerance",
        "clinicalStatus": {
            "coding": [
                {"system": "http://terminology.hl7.org/CodeSystem/allergyintolerance-clinical", "code": "active"}
            ]
        },
        "verificationStatus": {
            "coding": [
                {"system": "http://terminology.hl7.org/CodeSystem/allergyintolerance-verification", "code": "confirmed"}
            ]
        },
        "type": "allergy",
        "category": ["medication"] if n.get("allergy_class") else [],
        "code": {"text": n["substance"]},
        "patient": ref(patient_ref),
        "extension": _ext_confidence(item.get("confidence")) + _ext_org(org),
    }
    if not res["category"]:
        del res["category"]
    if n.get("criticality") in ("low", "high", "unable-to-assess"):
        res["criticality"] = n["criticality"]
    if n.get("recorded_date"):
        res["recordedDate"] = n["recorded_date"]
    if n.get("reaction"):
        res["reaction"] = [{"manifestation": [{"text": n["reaction"]}]}]
    return validate(res)


def diagnostic_report(*, patient_ref: str, date: str | None, org: dict | None, results: list[str], title: str) -> dict:
    res: dict[str, Any] = {
        "resourceType": "DiagnosticReport",
        "status": "final",
        "category": [
            {
                "coding": [
                    {"system": "http://terminology.hl7.org/CodeSystem/v2-0074", "code": "LAB", "display": "Laboratory"}
                ]
            }
        ],
        "code": {"text": title},
        "subject": ref(patient_ref),
        "result": [ref(r) for r in results],
    }
    if date:
        res["effectiveDateTime"] = date
    if org:
        res["performer"] = [org]
    return validate(res)


def provenance(
    *,
    target_ref: str,
    recorded_instant: str,
    agent: dict[str, Any],
    document_ref: str | None,
    page: int | None,
    snippet: str | None,
    activity: str = "CREATE",
) -> dict[str, Any]:
    res: dict[str, Any] = {
        "resourceType": "Provenance",
        "target": [ref(target_ref)],
        "recorded": recorded_instant,
        "activity": {
            "coding": [{"system": "http://terminology.hl7.org/CodeSystem/v3-DataOperation", "code": activity}]
        },
        "agent": [
            {
                "type": {
                    "coding": [
                        {
                            "system": "http://terminology.hl7.org/CodeSystem/provenance-participant-type",
                            "code": "author",
                        }
                    ]
                },
                "who": agent,
            }
        ],
    }
    if document_ref:
        entity_ext = []
        if page is not None:
            entity_ext.append({"url": EXT_SOURCE_PAGE, "valueInteger": page})
        if snippet:
            entity_ext.append({"url": EXT_SOURCE_SNIPPET, "valueString": snippet[:500]})
        entity: dict[str, Any] = {"role": "source", "what": ref(document_ref)}
        if entity_ext:
            entity["extension"] = entity_ext
        res["entity"] = [entity]
    return validate(res)
