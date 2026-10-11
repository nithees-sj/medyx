"""Doctor verification: matching rules, the decision table, and the end-to-end flows.

The register is replaced by an in-test provider (the real connector is an HTTP adapter whose
contract is tested separately with httpx.MockTransport). The AI is stubbed at its boundary.
"""

import json
import uuid
from datetime import date, timedelta
from pathlib import Path

import httpx
import pytest
from sqlalchemy import delete, select

from app.db import utcnow
from app.models import AuditEvent, Consent, DoctorDocument, DoctorProfile, Notification, TrustedDomain, User
from app.services.profiles import create_profile
from app.services.verification import matching, registry, service
from app.services.verification.certificate import CertificateFields
from app.services.verification.checks import CheckResult
from app.services.verification.policy import decide
from app.services.verification.registry import HttpRegistryProvider, RegistryError, RegistryRecord
from tests.conftest import login, make_user

ROOT_PNG = Path(__file__).resolve().parents[2] / "demo_data" / "rajan" / "anand_2025-04-02_rx.png"

# ───────────────────────────── matching ─────────────────────────────


@pytest.mark.parametrize(
    ("a", "b", "expected"),
    [
        ("Dr. Meena Raghavan", "Meena Raghavan", "exact"),
        ("Meena Raghavan", "MEENA R", "compatible"),
        ("Meena Raghavan", "R. Meena", "compatible"),
        ("Lakshmi Iyer", "Laxmi Iyer", "exact"),
        ("Meena Raghavan", "Meena Ragavan", "exact"),
        ("Priya Rajan", "Priya Ranjan", "compatible"),
        ("Meena Raghavan", "Meena Krishnan", "conflict"),
        ("Arjun Mehta", "Rahul Mehta", "conflict"),
        ("Meena", "Meena Raghavan Subramanian", "conflict"),
    ],
)
def test_name_match(a, b, expected):
    assert matching.name_match(a, b) == expected
    assert matching.name_match(b, a) == expected


def test_registration_council_and_domain_matching():
    assert matching.registration_match("TNMC-58213", "tnmc 58213") == "exact"
    assert matching.registration_match("TNMC-58213", "58213") == "digits"
    assert matching.registration_match("58213", "58231") == "conflict"
    assert matching.council_id("Tamil Nadu Medical Council") == "tamil_nadu"
    assert matching.council_id("TNMC") == "tamil_nadu"
    assert matching.council_id("Medical Council of India") == "nmc"
    assert matching.council_id("Arunachal Pradesh Medical Council") == "arunachal_pradesh"
    assert matching.council_id("Made-up Council") is None
    assert matching.domain_candidates("mail.kaveri.in") == ["mail.kaveri.in", "kaveri.in"]


# ───────────────────────────── decision table ─────────────────────────────


def _checks(**statuses):
    reason = statuses.pop("reason", None)
    out = []
    for kind in ("format", "duplicate", "registry", "identity", "document"):
        st = statuses.get(kind, "passed" if kind in ("format", "duplicate") else "missing")
        out.append(CheckResult(kind, st, "", details={"reason": reason} if kind == "registry" and reason else {}))
    return out


@pytest.mark.parametrize(
    ("statuses", "action", "risk"),
    [
        ({"registry": "passed", "identity": "passed"}, "approve", "low"),
        ({"registry": "passed", "identity": "passed", "document": "warning"}, "review", "low"),
        ({"registry": "passed", "identity": "missing", "document": "passed"}, "review", "low"),
        ({"registry": "passed", "identity": "missing"}, "review", "medium"),
        ({"registry": "failed", "reason": "not_found"}, "reject", "high"),
        ({"registry": "failed", "reason": "inactive", "identity": "passed"}, "reject", "high"),
        ({"registry": "failed", "reason": "name_mismatch"}, "review", "high"),
        ({"registry": "passed", "identity": "passed", "duplicate": "failed"}, "review", "high"),
        ({"registry": "not_configured", "identity": "passed", "document": "passed"}, "review", "low"),
        ({"registry": "not_configured", "document": "passed"}, "review", "medium"),
        ({"registry": "not_configured"}, "review", "medium"),
        ({"registry": "error", "document": "failed"}, "review", "high"),
    ],
)
def test_decision_table(statuses, action, risk):
    d = decide(_checks(**statuses), auto_approve=True, auto_reject=True)
    assert (d.action, d.risk) == (action, risk), d.reasons


def test_auto_actions_can_be_switched_off():
    assert (
        decide(_checks(registry="passed", identity="passed"), auto_approve=False, auto_reject=True).action == "review"
    )
    d = decide(_checks(registry="failed", reason="not_found"), auto_approve=True, auto_reject=False)
    assert (d.action, d.risk) == ("review", "high")


# ───────────────────────────── flows ─────────────────────────────


class FakeRegister:
    name = "test-register"

    def __init__(self, record: RegistryRecord | None = None, error: bool = False):
        self.record = record
        self.error = error
        self.calls: list[dict] = []

    async def lookup(self, **kw):
        self.calls.append(kw)
        if self.error:
            raise RegistryError("Register unreachable (ConnectError)")
        return self.record


ACTIVE_MEENA = RegistryRecord(
    found=True, name="MEENA R", registration_number="58213", council="Tamil Nadu Medical Council", status="Active"
)

APPLICATION = {
    "full_name": "Dr. Meena Raghavan",
    "specialty": "Nephrology",
    "organization": "Kaveri Kidney Care",
    "council": "Tamil Nadu Medical Council",
    "registration_number": "TNMC-58213",
}


async def apply(client, db, email: str, **overrides):
    user = await make_user(db, email=email, name="Applicant")
    login(client, user)
    r = await client.post("/api/onboarding/doctor", json={**APPLICATION, **overrides})
    assert r.status_code == 200, r.text
    await db.refresh(user)
    client.cookies.clear()  # drop the server-set cookie so login() below fully controls the session
    login(client, user)
    return user


async def test_no_register_means_human_review_with_evidence(client, db):
    admin = await make_user(db, email="admin@x.com", role="admin")
    user = await apply(client, db, "meena@gmail.com")
    decision = await service.run(db, user.id, trigger="test")
    assert (decision.action, decision.risk) == ("review", "medium")
    dp = await db.get(DoctorProfile, user.id)
    await db.refresh(dp)
    assert dp.verification_status == "pending"

    mine = (await client.get("/api/doctor/verification")).json()
    by = {c["kind"]: c["status"] for c in mine["checks"]}
    assert by == {
        "format": "passed",
        "duplicate": "passed",
        "registry": "not_configured",
        "identity": "missing",
        "document": "missing",
    }
    assert mine["can_update"] is True

    login(client, admin)
    rows = (await client.get("/api/admin/doctors")).json()
    assert rows[0]["risk"] == "medium" and len(rows[0]["checks"]) == 5
    cfg = (await client.get("/api/admin/verification/config")).json()
    assert cfg["registry"]["configured"] is False


async def test_register_plus_work_email_auto_approves(client, db, fhir):
    registry.set_provider(FakeRegister(ACTIVE_MEENA))
    db.add(TrustedDomain(domain="kaverikidney.in", organization="Kaveri Kidney Care"))
    await db.commit()
    user = await apply(client, db, "meena@mail.kaverikidney.in")
    decision = await service.run(db, user.id, trigger="test")
    assert decision.action == "approve"
    dp = await db.get(DoctorProfile, user.id)
    await db.refresh(dp)
    assert dp.verification_status == "verified" and dp.verification_method == "automatic"
    assert dp.verified_by is None and dp.next_check_at is not None
    assert fhir.store["Practitioner"][dp.fhir_practitioner_id]["name"][0]["text"] == "Dr. Meena Raghavan"
    note = await db.scalar(select(Notification).where(Notification.user_id == user.id))
    assert note.type == "doctor_verified"
    # A verified doctor can no longer edit details or upload certificates.
    assert (await client.put("/api/doctor/verification/details", json=APPLICATION)).status_code == 409


async def test_unknown_registration_is_rejected_and_resubmission_reruns(client, db):
    fake = FakeRegister(RegistryRecord(found=False))
    registry.set_provider(fake)
    user = await apply(client, db, "meena@gmail.com", registration_number="TNMC-99999")
    decision = await service.run(db, user.id, trigger="test")
    assert decision.action == "reject"
    dp = await db.get(DoctorProfile, user.id)
    await db.refresh(dp)
    assert dp.verification_status == "rejected" and "resubmit" in dp.review_note
    # The doctor fixes the number; the checks run again (here: explicitly) and land in review.
    r = await client.put("/api/doctor/verification/details", json=APPLICATION)
    assert r.status_code == 200
    fake.record = ACTIVE_MEENA
    uid = user.id
    db.expire_all()  # the API changed the row in another session (the app runs this in a fresh one)
    decision = await service.run(db, uid, trigger="resubmitted")
    dp = await db.get(DoctorProfile, uid)
    assert dp.verification_status == "pending" and decision.action == "review"
    assert fake.calls[-1]["registration_number"] == "TNMC-58213"


async def test_second_account_claiming_a_registration_is_high_risk(client, db):
    registry.set_provider(FakeRegister(ACTIVE_MEENA))
    admin = await make_user(db, email="admin@x.com", role="admin")
    await make_user(db, email="real@x.com", name="Dr. Meena Raghavan", role="doctor", doctor_status="verified")
    real = await db.get(DoctorProfile, (await db.scalar(select(DoctorProfile.user_id))))
    real.registration_number, real.council = "TNMC-58213", "Tamil Nadu Medical Council"
    await db.commit()
    impostor = await apply(client, db, "meena.r@gmail.com")
    decision = await service.run(db, impostor.id, trigger="test")
    assert (decision.action, decision.risk) == ("review", "high")
    assert await db.scalar(
        select(Notification).where(Notification.user_id == admin.id, Notification.type == "doctor_high_risk")
    )
    mine = (await client.get("/api/doctor/verification")).json()
    dup = next(c for c in mine["checks"] if c["kind"] == "duplicate")
    assert "other_user_ids" not in dup["details"]  # other accounts stay admin-only


async def test_certificate_is_read_and_compared(client, db, monkeypatch):
    user = await apply(client, db, "meena@gmail.com")

    async def fake_read(data, mime):
        assert data[:4] == b"\x89PNG" and mime == "image/png"
        return CertificateFields(
            document_type="registration_certificate",
            issuer="Tamil Nadu Medical Council",
            full_name="MEENA RAGHAVAN",
            registration_number="58213",
            council="Tamil Nadu Medical Council",
            registration_date=date(2009, 6, 1),
            qualification="MBBS, MD, DM (Nephrology)",
            confidence=0.93,
        )

    monkeypatch.setattr("app.services.verification.service.read_certificate", fake_read)
    r = await client.post(
        "/api/doctor/verification/certificate", files={"file": ("cert.png", ROOT_PNG.read_bytes(), "image/png")}
    )
    assert r.status_code == 202, r.text
    assert (await client.get("/api/doctor/verification")).json()["in_progress"] is True
    await service.process_certificate(uuid.UUID(r.json()["document_id"]))
    mine = (await client.get("/api/doctor/verification")).json()
    doc = next(c for c in mine["checks"] if c["kind"] == "document")
    assert doc["status"] == "passed" and doc["details"]["registration_match"] == "digits"
    assert mine["in_progress"] is False

    # A certificate with a different number is flagged, not approved.
    async def wrong_read(data, mime):
        return (await fake_read(data, mime)).model_copy(update={"registration_number": "61234"})

    monkeypatch.setattr("app.services.verification.service.read_certificate", wrong_read)
    r = await client.post(
        "/api/doctor/verification/certificate", files={"file": ("cert2.png", ROOT_PNG.read_bytes(), "image/png")}
    )
    decision_doc = uuid.UUID(r.json()["document_id"])
    await service.process_certificate(decision_doc)
    dp = await db.get(DoctorProfile, user.id)
    await db.refresh(dp)
    assert dp.verification_summary["risk"] == "high" and dp.verification_status == "pending"
    # Only PDF/JPG/PNG are accepted.
    bad = await client.post("/api/doctor/verification/certificate", files={"file": ("x.txt", b"hello", "text/plain")})
    assert bad.status_code == 422


async def test_certificate_file_is_admin_only(client, db):
    admin = await make_user(db, email="admin@x.com", role="admin")
    patient = await make_user(db, email="p@x.com", role="patient")
    user = await apply(client, db, "meena@gmail.com")
    await client.post(
        "/api/doctor/verification/certificate", files={"file": ("cert.png", ROOT_PNG.read_bytes(), "image/png")}
    )
    login(client, patient)
    assert (await client.get(f"/api/admin/doctors/{user.id}/certificate")).status_code == 403
    login(client, admin)
    r = await client.get(f"/api/admin/doctors/{user.id}/certificate")
    assert r.status_code == 200 and r.content[:4] == b"\x89PNG"


async def test_recheck_suspends_and_ends_shares(client, db):
    owner = await make_user(db, email="priya@x.com", role="patient")
    doctor = await make_user(db, email="d@x.com", name="Dr. Meena", role="doctor", doctor_status="verified")
    profile = await create_profile(
        db, owner_user_id=owner.id, display_name="Rajan", relationship="parent", dob=date(1962, 5, 14),
        sex="male", blood_group="B+", emergency_contact_name=None, emergency_contact_phone=None,
    )  # fmt: skip
    db.add(
        Consent(
            profile_id=profile.id,
            granted_by_user_id=owner.id,
            doctor_user_id=doctor.id,
            scopes=["labs"],
            status="active",
            duration_hours=168,
            expires_at=utcnow() + timedelta(days=7),
        )  # fmt: skip
    )
    await db.commit()

    # A register outage decides nothing.
    registry.set_provider(FakeRegister(error=True))
    assert "register errors 1" in await service.recheck_due()
    dp = await db.get(DoctorProfile, doctor.id)
    await db.refresh(dp)
    assert dp.verification_status == "verified"

    dp.next_check_at = utcnow() - timedelta(minutes=1)
    await db.commit()
    registry.set_provider(FakeRegister(RegistryRecord(found=True, name="Dr. Meena", status="Suspended")))
    doctor_id, owner_id, profile_id = doctor.id, owner.id, profile.id
    assert "suspended 1" in await service.recheck_due()
    db.expire_all()
    dp = await db.get(DoctorProfile, doctor_id)
    assert dp.verification_status == "suspended" and dp.verification_method == "registry recheck"
    consent = await db.scalar(select(Consent))
    assert consent.status == "revoked"
    ev = await db.scalar(select(AuditEvent).where(AuditEvent.profile_id == profile_id))
    assert ev.details == {"event": "revoked", "reason": "doctor_suspended"}
    assert await db.scalar(
        select(Notification).where(Notification.user_id == owner_id, Notification.type == "access_revoked")
    )
    login(client, await db.get(User, doctor_id))
    assert (await client.get(f"/api/profiles/{profile_id}/timeline")).status_code == 403


async def test_admin_suspend_reinstate_and_trusted_domains(client, db):
    admin = await make_user(db, email="admin@x.com", role="admin")
    doctor = await make_user(db, email="d@x.com", role="doctor", doctor_status="verified")
    login(client, admin)
    assert (await client.post(f"/api/admin/doctors/{doctor.id}/suspend", json={})).status_code == 422
    r = await client.post(f"/api/admin/doctors/{doctor.id}/suspend", json={"note": "Complaint under review"})
    assert r.json()["verification_status"] == "suspended"
    assert (await client.get("/api/admin/doctors?status_filter=suspended")).json()[0]["user_id"] == str(doctor.id)
    r = await client.post(f"/api/admin/doctors/{doctor.id}/reinstate", json={"note": "Cleared"})
    assert r.json()["verification_status"] == "verified" and r.json()["verification_method"] == "admin"

    assert (
        await client.post("/api/admin/trusted-domains", json={"domain": "gmail.com", "organization": "X"})
    ).status_code == 422
    r = await client.post(
        "/api/admin/trusted-domains", json={"domain": "@KaveriKidney.in", "organization": "Kaveri Kidney Care"}
    )
    assert r.status_code == 201 and r.json()["domain"] == "kaverikidney.in"
    assert (
        await client.post("/api/admin/trusted-domains", json={"domain": "kaverikidney.in", "organization": "Other"})
    ).status_code == 409
    assert [d["domain"] for d in (await client.get("/api/admin/trusted-domains")).json()] == ["kaverikidney.in"]
    assert (await client.delete("/api/admin/trusted-domains/kaverikidney.in")).status_code == 204


# ───────────────────────────── HTTP register contract ─────────────────────────────


async def test_http_register_contract():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["auth"] = request.headers.get("authorization")
        seen["body"] = json.loads(request.content)
        n = seen["body"]["registration_number"]
        if n == "MISSING":
            return httpx.Response(404)
        if n == "BROKEN":
            return httpx.Response(502)
        if n == "GARBAGE":
            return httpx.Response(200, json={"status": "ok"})
        return httpx.Response(
            200,
            json={
                "found": True,
                "name": "MEENA R",
                "registration_number": "58213",
                "status": "Active",
                "council": "Tamil Nadu Medical Council",
                "registration_year": "2009",
            },  # fmt: skip
        )

    p = HttpRegistryProvider("https://register.example/lookup", "k3y", 5, transport=httpx.MockTransport(handler))
    kw = {"council": "TNMC", "council_id": "tamil_nadu", "full_name": "Dr. Meena Raghavan"}
    rec = await p.lookup(registration_number="TNMC-58213", **kw)
    assert rec.found and rec.active and rec.registration_year == 2009
    assert seen["auth"] == "Bearer k3y" and seen["body"]["council_id"] == "tamil_nadu"
    assert (await p.lookup(registration_number="MISSING", **kw)).found is False
    for bad in ("BROKEN", "GARBAGE"):
        with pytest.raises(RegistryError):
            await p.lookup(registration_number=bad, **kw)


async def test_document_rows_are_scoped_to_the_doctor(db):
    # Sanity: certificates are tied to the doctor's user row and cascade with it.
    user = await make_user(db, email="d@x.com", role="doctor", doctor_status="pending")
    db.add(
        DoctorDocument(
            doctor_user_id=user.id, original_filename="c.png", mime="image/png", storage_path="/x", sha256="0"
        )
    )
    await db.commit()
    await db.execute(delete(User).where(User.id == user.id))
    await db.commit()
    assert await db.scalar(select(DoctorDocument)) is None
