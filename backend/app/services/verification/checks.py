"""The evidence collected for a doctor. Each check is independent and returns a CheckResult;
policy.py turns the set into a decision."""

from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import DoctorDocument, DoctorProfile, TrustedDomain, User
from app.services.verification import matching
from app.services.verification.registry import RegistryError, RegistryProvider


@dataclass
class CheckResult:
    kind: str  # format | duplicate | registry | identity | document
    status: str  # passed | warning | failed | missing | not_configured | error
    summary: str  # one sentence a reviewer (and, for most checks, the doctor) can read
    provider: str | None = None
    details: dict[str, Any] = field(default_factory=dict)


def format_check(dp: DoctorProfile) -> CheckResult:
    cid = matching.council_id(dp.council)
    reg = matching.normalize_registration(dp.registration_number)
    problems = []
    if cid is None:
        problems.append(f"council “{dp.council}” isn't a recognised Indian medical council")
    if not any(c.isdigit() for c in reg) or not 3 <= len(reg) <= 20:
        problems.append("the registration number doesn't look like one")
    details = {"council_id": cid, "council_name": matching.council_name(cid), "registration_normalized": reg}
    if problems:
        return CheckResult("format", "warning", "Check the details: " + "; ".join(problems) + ".", details=details)
    return CheckResult(
        "format", "passed", f"{matching.council_name(cid)} · registration {dp.registration_number}", details=details
    )


async def duplicate_check(db: AsyncSession, dp: DoctorProfile) -> CheckResult:
    """Register data is partly public, so two accounts claiming one registration is the classic
    impersonation signal."""
    reg = matching.normalize_registration(dp.registration_number)
    cid = matching.council_id(dp.council)
    others = (
        await db.scalars(
            select(DoctorProfile).where(
                DoctorProfile.user_id != dp.user_id,
                DoctorProfile.verification_status.in_(["pending", "verified", "suspended"]),
            )
        )
    ).all()
    clashes = [
        o
        for o in others
        if matching.normalize_registration(o.registration_number) == reg
        and (cid is None or matching.council_id(o.council) in (cid, None))
    ]
    if clashes:
        statuses = sorted({o.verification_status for o in clashes})
        return CheckResult(
            "duplicate",
            "failed",
            f"This registration number is also claimed by {len(clashes)} other account(s) ({', '.join(statuses)}).",
            details={"other_user_ids": [str(o.user_id) for o in clashes], "other_statuses": statuses},
        )
    return CheckResult("duplicate", "passed", "No other account claims this registration number.")


async def registry_check(dp: DoctorProfile, provider: RegistryProvider | None) -> CheckResult:
    if provider is None:
        return CheckResult(
            "registry",
            "not_configured",
            "No medical-register connection is configured, so the licence couldn't be checked automatically.",
        )
    cid = matching.council_id(dp.council)
    try:
        rec = await provider.lookup(
            council=dp.council, council_id=cid, registration_number=dp.registration_number, full_name=dp.full_name
        )
    except RegistryError as e:
        return CheckResult("registry", "error", f"The register couldn't be checked: {e}.", provider=provider.name)
    details: dict[str, Any] = {
        "registry_name": rec.name,
        "registry_status": rec.status,
        "registry_council": rec.council,
        "registry_number": rec.registration_number,
        "qualification": rec.qualification,
        "registration_year": rec.registration_year,
    }
    if not rec.found:
        details["reason"] = "not_found"
        return CheckResult(
            "registry",
            "failed",
            f"No registration {dp.registration_number} was found in the {dp.council} register.",
            provider=provider.name,
            details=details,
        )
    if not rec.active:
        details["reason"] = "inactive"
        return CheckResult(
            "registry",
            "failed",
            f"The register lists this registration as “{rec.status or 'unknown'}”, not active.",
            provider=provider.name,
            details=details,
        )
    name = matching.name_match(dp.full_name, rec.name or "") if rec.name else "conflict"
    details["name_match"] = name
    if name == "conflict":
        details["reason"] = "name_mismatch"
        return CheckResult(
            "registry",
            "failed",
            f"The register has this number under a different name (“{rec.name or 'no name'}”).",
            provider=provider.name,
            details=details,
        )
    if rec.council and cid and matching.council_id(rec.council) not in (cid, None):
        details["reason"] = "council_mismatch"
        return CheckResult(
            "registry",
            "warning",
            f"Active registration found, but under {rec.council} rather than {dp.council}.",
            provider=provider.name,
            details=details,
        )
    how = "exactly" if name == "exact" else "(name written differently)"
    return CheckResult(
        "registry",
        "passed",
        f"Active registration found for {rec.name} {how}.",
        provider=provider.name,
        details=details,
    )


async def identity_check(db: AsyncSession, user: User, dp: DoctorProfile) -> CheckResult:
    """Is the person signing in bound to a real organisation? Google has verified that they control
    their email address; an admin-trusted hospital domain therefore ties them to that hospital."""
    domain = matching.email_domain(user.email)
    if domain in matching.PUBLIC_EMAIL_DOMAINS:
        return CheckResult(
            "identity",
            "missing",
            f"Signed in with a personal address (@{domain}); not linked to a hospital.",
            details={"domain": domain},
        )
    trusted = None
    for cand in matching.domain_candidates(domain):
        trusted = await db.get(TrustedDomain, cand)
        if trusted:
            break
    if trusted is None:
        return CheckResult(
            "identity",
            "missing",
            f"@{domain} isn't on the trusted hospital domains list.",
            details={"domain": domain},
        )
    details = {"domain": domain, "trusted_domain": trusted.domain, "organization": trusted.organization}
    if not matching.org_overlap(trusted.organization, dp.organization):
        return CheckResult(
            "identity",
            "warning",
            f"Work email at {trusted.organization}, but the profile says “{dp.organization}”.",
            details=details,
        )
    return CheckResult(
        "identity",
        "passed",
        f"Signed in with a verified {trusted.organization} work email (@{domain}).",
        details=details,
    )


async def document_check(db: AsyncSession, dp: DoctorProfile) -> CheckResult:
    doc = await db.scalar(
        select(DoctorDocument)
        .where(DoctorDocument.doctor_user_id == dp.user_id)
        .order_by(DoctorDocument.created_at.desc())
    )
    if doc is None:
        return CheckResult("document", "missing", "No registration certificate uploaded.")
    ex = doc.extracted or {}
    if not ex or ex.get("error"):
        return CheckResult(
            "document",
            "error",
            "The certificate couldn't be read automatically" + (f" ({ex['error']})." if ex.get("error") else "."),
            provider="gemini",
            details={"document_id": str(doc.id)},
        )
    name = matching.name_match(dp.full_name, ex.get("full_name") or "") if ex.get("full_name") else None
    reg = (
        matching.registration_match(dp.registration_number, ex["registration_number"])
        if ex.get("registration_number")
        else None
    )
    council = None
    if ex.get("council") or ex.get("issuer"):
        found = matching.council_id(ex.get("council") or ex.get("issuer") or "")
        council = (
            "match" if found and found == matching.council_id(dp.council) else ("unknown" if not found else "conflict")
        )
    details = {
        "document_id": str(doc.id),
        "read": {
            k: ex.get(k)
            for k in (
                "document_type",
                "issuer",
                "full_name",
                "registration_number",
                "council",
                "registration_date",
                "qualification",
            )
        },  # fmt: skip
        "confidence": ex.get("confidence"),
        "concerns": ex.get("concerns") or [],
        "name_match": name,
        "registration_match": reg,
        "council_match": council,
    }
    if name == "conflict" or reg == "conflict" or council == "conflict":
        bad = [w for w, v in (("name", name), ("registration number", reg), ("council", council)) if v == "conflict"]
        return CheckResult(
            "document",
            "failed",
            f"The certificate's {', '.join(bad)} doesn't match the details entered (read by AI).",
            provider="gemini",
            details=details,
        )
    complete = ex.get("document_type") == "registration_certificate" and name and reg and council == "match"
    if complete and (ex.get("confidence") or 0) >= 0.7 and not ex.get("concerns"):
        return CheckResult(
            "document",
            "passed",
            "Registration certificate matches the name, number and council entered (read by AI).",
            provider="gemini",
            details=details,
        )
    gaps = []
    if ex.get("document_type") != "registration_certificate":
        gaps.append(
            f"it's a {str(ex.get('document_type') or 'document').replace('_', ' ')}, not a registration certificate"
        )
    if not reg:
        gaps.append("no registration number was readable")
    if (ex.get("confidence") or 0) < 0.7:
        gaps.append("parts were hard to read")
    if ex.get("concerns"):
        gaps.append("the reader noted concerns")
    return CheckResult(
        "document",
        "warning",
        "Certificate partly matches: " + ("; ".join(gaps) or "some fields couldn't be compared") + " (read by AI).",
        provider="gemini",
        details=details,
    )
