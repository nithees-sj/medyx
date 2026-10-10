"""Stage 6: write one FHIR transaction Bundle per document.

Bundle = (new Organization/Practitioner) + DocumentReference + Encounter + clinical
resources + one Provenance per resource (entity = the DocumentReference, with the
source page and snippet) + DiagnosticReport for lab reports.
"""

import base64
import hashlib
import uuid
from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Any

from rapidfuzz import fuzz

from app import knowledge as kb
from app.services import fhir_resources as fr
from app.services.fhir_client import get_fhir
from app.services.ingest.merge import Planned

ENCOUNTER_TYPES = {"opd_note", "prescription", "discharge_summary"}


def now_instant() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


def _urn() -> str:
    return f"urn:uuid:{uuid.uuid4()}"


@dataclass
class Entry:
    full_url: str
    resource: dict[str, Any]
    method: str = "POST"


async def find_or_plan_organization(name: str | None, address: str | None, entries: list[Entry]) -> dict | None:
    """Fuzzy-match an existing Organization by name; otherwise add a new one to the bundle."""
    if not name:
        return None
    clean = name.strip()
    for org in await get_fhir().search("Organization", {"_count": 500}):
        if fuzz.token_set_ratio(kb.norm_text(org.get("name", "")), kb.norm_text(clean)) >= 90:
            return fr.ref(f"Organization/{org['id']}", org.get("name"))
    # Title-case ALL-CAPS letterheads for display ("ANAND FAMILY CLINIC" → "Anand Family Clinic").
    display = clean.title() if clean.isupper() else clean
    e = Entry(_urn(), fr.organization(display, address))
    entries.append(e)
    return fr.ref(e.full_url, display)


async def find_or_plan_practitioner(name: str | None, specialty: str | None, entries: list[Entry]) -> dict | None:
    if not name:
        return None
    clean = name.strip()
    family = clean.replace("Dr.", "").replace("Dr ", "").split()[-1]
    for p in await get_fhir().search("Practitioner", {"name": family, "_count": 50}):
        texts = [n.get("text", "") for n in p.get("name", [])]
        if any(fuzz.token_set_ratio(kb.norm_text(t), kb.norm_text(clean)) >= 90 for t in texts):
            return fr.ref(f"Practitioner/{p['id']}", clean)
    e = Entry(_urn(), fr.document_practitioner(clean, specialty))
    entries.append(e)
    return fr.ref(e.full_url, clean)


def build_resource(
    p: Planned, *, patient_ref: str, encounter_ref: str | None, org: dict | None, requester: dict | None
) -> dict[str, Any] | None:
    n, raw = p.normalized, p.raw
    if p.kind == "Condition":
        return fr.condition(n, patient_ref=patient_ref, encounter_ref=encounter_ref, org=org, item=raw)
    if p.kind == "MedicationRequest":
        return fr.medication_request(
            n, patient_ref=patient_ref, encounter_ref=encounter_ref, requester=requester, org=org, item=raw
        )
    if p.kind == "AllergyIntolerance":
        return fr.allergy_intolerance(n, patient_ref=patient_ref, org=org, item=raw)
    if p.kind == "Observation":
        return fr.lab_observation(n, patient_ref=patient_ref, org=org, item=raw)
    if p.kind == "Vital":
        return fr.vital_observation(n, patient_ref=patient_ref, encounter_ref=encounter_ref, org=org, item=raw)
    return None


def _bundle(entries: list[Entry]) -> dict[str, Any]:
    return {
        "resourceType": "Bundle",
        "type": "transaction",
        "entry": [
            {
                "fullUrl": e.full_url,
                "resource": e.resource,
                "request": {"method": e.method, "url": e.resource["resourceType"]},
            }
            for e in entries
        ],
    }


async def submit(entries: list[Entry]) -> dict[str, str]:
    """POST the transaction; return {fullUrl: "Type/id"} for every entry."""
    resp = await get_fhir().transaction(_bundle(entries))
    out: dict[str, str] = {}
    for e, r in zip(entries, resp.get("entry", []), strict=True):
        location = r["response"]["location"]  # e.g. "Observation/123/_history/1"
        parts = location.split("/")
        out[e.full_url] = f"{parts[0]}/{parts[1]}"
    return out


@dataclass
class DocumentWrite:
    doc_id: str
    filename: str
    mime: str
    data: bytes
    created_at: datetime
    document_type: str
    document_date: date | None
    org_name: str | None
    org_address: str | None
    practitioner_name: str | None
    practitioner_specialty: str | None
    encounter_reason: str | None


async def write_document(
    *,
    patient_ref: str,
    doc: DocumentWrite,
    planned: list[Planned],
    agent: dict[str, Any],
    existing_docref: str | None = None,
) -> tuple[str, dict[Any, str]]:
    """Write the document bundle. Returns (DocumentReference ref, {item_id: resource ref}).

    With `existing_docref` (items confirmed later from the review queue) only the clinical
    resources and their Provenance are written, pointing at the existing DocumentReference.
    """
    entries: list[Entry] = []
    org = await find_or_plan_organization(doc.org_name, doc.org_address, entries)
    practitioner = await find_or_plan_practitioner(doc.practitioner_name, doc.practitioner_specialty, entries)
    doc_date = doc.document_date.isoformat() if doc.document_date else None

    if existing_docref:
        return existing_docref, await _write_items_only(
            entries,
            planned,
            patient_ref=patient_ref,
            org=org,
            practitioner=practitioner,
            agent=agent,
            docref=existing_docref,
        )

    docref = Entry(
        _urn(),
        fr.document_reference(
            patient_ref=patient_ref,
            doc_id=doc.doc_id,
            doc_type=doc.document_type,
            title=doc.filename,
            content_type=doc.mime,
            url=f"/api/documents/{doc.doc_id}/file",
            size=len(doc.data),
            sha1_b64=base64.b64encode(hashlib.sha1(doc.data).digest()).decode(),
            created_instant=doc.created_at.astimezone(UTC).replace(microsecond=0).isoformat(),
            document_date=doc_date,
            author=org,
        ),
    )
    entries.append(docref)

    encounter_ref = None
    if doc.document_type in ENCOUNTER_TYPES:
        enc = Entry(
            _urn(),
            fr.encounter(
                patient_ref=patient_ref, date=doc_date, org=org, practitioner=practitioner, reason=doc.encounter_reason
            ),
        )
        entries.append(enc)
        encounter_ref = enc.full_url

    recorded = now_instant()
    item_refs: dict[Any, str] = {}
    batch_urls: list[str | None] = []
    lab_results: list[str] = []
    for p in planned:
        page = p.raw.get("page")
        snippet = p.raw.get("snippet")
        if p.existing_ref:
            target, activity = p.existing_ref, "UPDATE"
            batch_urls.append(None)
        elif p.batch_key is not None and batch_urls[p.batch_key]:
            target, activity = batch_urls[p.batch_key] or "", "UPDATE"
            batch_urls.append(None)
        else:
            resource = build_resource(
                p, patient_ref=patient_ref, encounter_ref=encounter_ref, org=org, requester=practitioner
            )
            if resource is None:
                batch_urls.append(None)
                continue
            e = Entry(_urn(), resource)
            entries.append(e)
            target, activity = e.full_url, "CREATE"
            batch_urls.append(e.full_url)
        item_refs[p.item_id] = target
        if p.kind == "Observation" and target not in lab_results:
            lab_results.append(target)
        entries.append(
            Entry(
                _urn(),
                fr.provenance(
                    target_ref=target,
                    recorded_instant=recorded,
                    agent=agent,
                    document_ref=docref.full_url,
                    page=page,
                    snippet=snippet,
                    activity=activity,
                ),
            )
        )

    if doc.document_type == "lab_report" and lab_results:
        entries.append(
            Entry(
                _urn(),
                fr.diagnostic_report(
                    patient_ref=patient_ref,
                    date=doc_date,
                    org=org,
                    results=lab_results,
                    title=f"Laboratory report — {doc.org_name or 'unknown lab'}",
                ),
            )
        )

    ids = await submit(entries)
    resolved = {item: ids.get(ref, ref) for item, ref in item_refs.items()}
    return ids[docref.full_url], resolved


async def _write_items_only(
    entries: list[Entry],
    planned: list[Planned],
    *,
    patient_ref: str,
    org: dict | None,
    practitioner: dict | None,
    agent: dict[str, Any],
    docref: str,
) -> dict[Any, str]:
    recorded = now_instant()
    item_refs: dict[Any, str] = {}
    for p in planned:
        if p.existing_ref:
            target, activity = p.existing_ref, "UPDATE"
        else:
            resource = build_resource(p, patient_ref=patient_ref, encounter_ref=None, org=org, requester=practitioner)
            if resource is None:
                continue
            e = Entry(_urn(), resource)
            entries.append(e)
            target, activity = e.full_url, "CREATE"
        item_refs[p.item_id] = target
        entries.append(
            Entry(
                _urn(),
                fr.provenance(
                    target_ref=target,
                    recorded_instant=recorded,
                    agent=agent,
                    document_ref=docref,
                    page=p.raw.get("page"),
                    snippet=p.raw.get("snippet"),
                    activity=activity,
                ),
            )
        )
    if not entries:
        return item_refs
    ids = await submit(entries)
    return {item: ids.get(ref, ref) for item, ref in item_refs.items()}
