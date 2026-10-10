"""In-memory stand-in for the HAPI FHIR server, used by API tests that don't need real HAPI."""

import copy
import itertools
from typing import Any

from app.services.fhir_client import FhirError


class FakeFhirClient:
    def __init__(self) -> None:
        self.store: dict[str, dict[str, dict[str, Any]]] = {}
        self._ids = itertools.count(1)

    async def aclose(self) -> None:
        pass

    async def metadata(self) -> dict[str, Any]:
        return {"resourceType": "CapabilityStatement", "fhirVersion": "4.0.1"}

    def _put(self, resource: dict[str, Any], rid: str | None = None) -> dict[str, Any]:
        r = copy.deepcopy(resource)
        r["id"] = rid or r.get("id") or f"f{next(self._ids)}"
        self.store.setdefault(r["resourceType"], {})[r["id"]] = r
        return copy.deepcopy(r)

    async def create(self, resource: dict[str, Any]) -> dict[str, Any]:
        r = dict(resource)
        r.pop("id", None)
        return self._put(r)

    async def read(self, resource_type: str, rid: str) -> dict[str, Any]:
        try:
            return copy.deepcopy(self.store[resource_type][rid])
        except KeyError as e:
            raise FhirError(404, "not found") from e

    async def update(self, resource: dict[str, Any]) -> dict[str, Any]:
        return self._put(resource, resource["id"])

    async def delete(self, resource_type: str, rid: str) -> None:
        self.store.get(resource_type, {}).pop(rid, None)

    async def search(self, resource_type: str, params: dict[str, Any]) -> list[dict[str, Any]]:
        out = []
        for r in self.store.get(resource_type, {}).values():
            if _matches(r, params):
                out.append(copy.deepcopy(r))
        return out

    async def transaction(self, bundle: dict[str, Any]) -> dict[str, Any]:
        # Assign ids to urn:uuid fullUrls first, then rewrite references.
        mapping: dict[str, str] = {}
        entries = bundle.get("entry", [])
        for e in entries:
            req = e["request"]
            res = e["resource"]
            if req["method"] == "POST":
                rid = f"f{next(self._ids)}"
                mapping[e.get("fullUrl", "")] = f"{res['resourceType']}/{rid}"
                e["_id"] = rid
        responses = []
        for e in entries:
            res = _rewrite_refs(copy.deepcopy(e["resource"]), mapping)
            if e["request"]["method"] == "POST":
                saved = self._put(res, e["_id"])
            else:
                saved = self._put(res, res["id"])
            responses.append(
                {
                    "response": {
                        "status": "201 Created",
                        "location": f"{saved['resourceType']}/{saved['id']}/_history/1",
                    }
                }
            )
        return {"resourceType": "Bundle", "type": "transaction-response", "entry": responses}


def _rewrite_refs(node: Any, mapping: dict[str, str]) -> Any:
    if isinstance(node, dict):
        return {
            k: (mapping.get(v, v) if k == "reference" and isinstance(v, str) else _rewrite_refs(v, mapping))
            for k, v in node.items()
        }
    if isinstance(node, list):
        return [_rewrite_refs(v, mapping) for v in node]
    return node


def _matches(r: dict[str, Any], params: dict[str, Any]) -> bool:
    for key, value in params.items():
        if key.startswith("_"):
            continue
        if key in ("patient", "subject"):
            ref = (r.get("subject") or r.get("patient") or {}).get("reference", "")
            if ref != value and ref.split("/")[-1] != str(value).split("/")[-1]:
                return False
        elif key == "target":
            refs = [t.get("reference") for t in r.get("target", [])]
            if value not in refs:
                return False
    return True
