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
