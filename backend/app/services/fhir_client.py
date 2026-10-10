"""Thin async client for the HAPI FHIR R4 server."""

import logging
from typing import Any

import httpx

from app.config import get_settings

log = logging.getLogger(__name__)

FHIR_JSON = "application/fhir+json"


class FhirError(RuntimeError):
    def __init__(self, status: int, message: str):
        super().__init__(f"FHIR {status}: {message}")
        self.status = status


class FhirClient:
    def __init__(self, base_url: str, http: httpx.AsyncClient | None = None):
        self.base_url = base_url.rstrip("/")
        self._http = http or httpx.AsyncClient(
            timeout=httpx.Timeout(30.0, connect=5.0),
            headers={"Accept": FHIR_JSON, "Content-Type": FHIR_JSON},
        )

    async def aclose(self) -> None:
        await self._http.aclose()

    async def _request(self, method: str, path: str, **kwargs: Any) -> dict[str, Any]:
        url = path if path.startswith("http") else f"{self.base_url}/{path.lstrip('/')}"
        resp = await self._http.request(method, url, **kwargs)
        if resp.status_code >= 400:
            # Log status + resource path only (never bodies, which may contain PHI).
            log.warning("FHIR %s %s -> %s", method, path.split("?")[0], resp.status_code)
            raise FhirError(resp.status_code, _outcome_text(resp))
        if not resp.content:
            return {}
        return resp.json()

    async def metadata(self) -> dict[str, Any]:
        return await self._request("GET", "metadata", timeout=5.0)

    async def read(self, resource_type: str, rid: str) -> dict[str, Any]:
        return await self._request("GET", f"{resource_type}/{rid}")

    async def create(self, resource: dict[str, Any]) -> dict[str, Any]:
        return await self._request("POST", resource["resourceType"], json=resource)

    async def update(self, resource: dict[str, Any]) -> dict[str, Any]:
        return await self._request("PUT", f"{resource['resourceType']}/{resource['id']}", json=resource)

    async def delete(self, resource_type: str, rid: str) -> None:
        await self._request("DELETE", f"{resource_type}/{rid}")

    async def transaction(self, bundle: dict[str, Any]) -> dict[str, Any]:
        return await self._request("POST", "", json=bundle)

    async def search(self, resource_type: str, params: dict[str, Any]) -> list[dict[str, Any]]:
        """Search and follow `next` links; returns all matching resources."""
        params = {"_count": 200, **params}
        bundle = await self._request("GET", resource_type, params=params)
        out: list[dict[str, Any]] = []
        while True:
            for entry in bundle.get("entry", []):
                if entry.get("search", {}).get("mode", "match") == "match":
                    out.append(entry["resource"])
            nxt = next((link["url"] for link in bundle.get("link", []) if link["relation"] == "next"), None)
            if not nxt:
                return out
            bundle = await self._request("GET", _rebase(nxt, self.base_url))


def _rebase(url: str, base_url: str) -> str:
    """HAPI paging links use its configured server_address; keep requests on our base URL."""
    if "?" in url:
        return f"{base_url}?{url.split('?', 1)[1]}"
    return url


def _outcome_text(resp: httpx.Response) -> str:
    try:
        body = resp.json()
        issues = body.get("issue", [])
        return "; ".join(i.get("diagnostics", "") for i in issues)[:500] or resp.reason_phrase
    except ValueError:
        return resp.reason_phrase


_client: FhirClient | None = None


def get_fhir() -> FhirClient:
    global _client
    if _client is None:
        _client = FhirClient(get_settings().fhir_base_url)
    return _client


def set_fhir(client: FhirClient | None) -> None:
    """Used by tests to swap in a fake FHIR client."""
    global _client
    _client = client
