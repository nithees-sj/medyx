"""Medical-register lookups (is this registration real and active?).

No vendor publishes its NMC/state-council API openly, so HealthThread speaks one small JSON
contract (docs/VERIFICATION.md) and you point REGISTRY_URL at it — either a vendor that
already matches it or a thin adapter in front of one (Surepass, Decentro, ABDM HPR …).
Until REGISTRY_PROVIDER is set the registry check reports "not configured" and nothing is
approved on registry grounds. Responses are never invented.
"""

from dataclasses import dataclass
from typing import Protocol

import httpx

from app.config import get_settings


@dataclass(frozen=True)
class RegistryRecord:
    found: bool
    name: str | None = None
    registration_number: str | None = None
    council: str | None = None
    status: str | None = None  # "active" | "suspended" | "cancelled" | "expired" | other text
    qualification: str | None = None
    registration_year: int | None = None

    @property
    def active(self) -> bool:
        return (self.status or "").strip().lower() in ("active", "valid", "registered", "current")


class RegistryError(Exception):
    """The register couldn't be reached or answered nonsense; retry later, decide nothing."""


class RegistryProvider(Protocol):
    name: str

    async def lookup(
        self, *, council: str, council_id: str | None, registration_number: str, full_name: str
    ) -> RegistryRecord: ...


class HttpRegistryProvider:
    """POST {REGISTRY_URL} with a bearer key; see docs/VERIFICATION.md for the contract."""

    name = "http"

    def __init__(self, url: str, api_key: str, timeout: float, transport: httpx.AsyncBaseTransport | None = None):
        self.url = url
        self.api_key = api_key
        self.timeout = timeout
        self.transport = transport

    async def lookup(
        self, *, council: str, council_id: str | None, registration_number: str, full_name: str
    ) -> RegistryRecord:
        headers = {"Authorization": f"Bearer {self.api_key}"} if self.api_key else {}
        body = {
            "council": council,
            "council_id": council_id,
            "registration_number": registration_number,
            "full_name": full_name,
        }
        try:
            async with httpx.AsyncClient(timeout=self.timeout, transport=self.transport) as client:
                resp = await client.post(self.url, json=body, headers=headers)
        except httpx.HTTPError as e:
            raise RegistryError(f"Register unreachable ({type(e).__name__})") from e
        if resp.status_code == 404:
            return RegistryRecord(found=False)
        if resp.status_code >= 400:
            raise RegistryError(f"Register returned HTTP {resp.status_code}")
        try:
            data = resp.json()
        except ValueError as e:
            raise RegistryError("Register returned invalid JSON") from e
        if not isinstance(data, dict) or not isinstance(data.get("found"), bool):
            raise RegistryError("Register response is missing the boolean 'found' field")
        year = data.get("registration_year")
        return RegistryRecord(
            found=data["found"],
            name=_str(data.get("name")),
            registration_number=_str(data.get("registration_number")),
            council=_str(data.get("council")),
            status=_str(data.get("status")),
            qualification=_str(data.get("qualification")),
            registration_year=int(year) if isinstance(year, int | str) and str(year).isdigit() else None,
        )


def _str(v: object) -> str | None:
    return str(v).strip()[:300] if v not in (None, "") else None


_override: RegistryProvider | None = None


def set_provider(provider: RegistryProvider | None) -> None:
    """Tests (and future built-in vendors) can install a provider explicitly."""
    global _override
    _override = provider


def get_provider() -> RegistryProvider | None:
    if _override is not None:
        return _override
    s = get_settings()
    if s.registry_provider == "http" and s.registry_url:
        return HttpRegistryProvider(s.registry_url, s.registry_api_key, s.registry_timeout_seconds)
    return None


def describe() -> dict[str, object]:
    p = get_provider()
    s = get_settings()
    return {
        "configured": p is not None,
        "provider": p.name if p else None,
        "url_host": httpx.URL(s.registry_url).host if p is not None and s.registry_url else None,
    }
