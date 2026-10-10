import re

import pytest
from sqlalchemy import select

from app.models import DoctorProfile, HealthProfile, Notification, User
from app.security import SESSION_COOKIE
from app.services.google_auth import GoogleAuthError
from tests.conftest import login, make_user

CLAIMS = {
    "sub": "google-sub-123",
    "email": "new.user@gmail.com",
    "email_verified": True,
    "name": "New User",
    "picture": "https://example.com/a.png",
    "aud": "test-client-id",
}


@pytest.fixture
def google_ok(monkeypatch):
    async def fake_verify(credential: str):
        return dict(CLAIMS)

    monkeypatch.setattr("app.routers.auth.verify_google_token", fake_verify)


async def test_google_login_creates_user_and_sets_httponly_cookie(client, google_ok, db):
    resp = await client.post("/api/auth/google", json={"credential": "x" * 40})
    assert resp.status_code == 200
    body = resp.json()
    assert body["redirect"] == "/onboarding"
    assert body["user"]["role"] is None
    cookie = resp.headers["set-cookie"]
    assert SESSION_COOKIE in cookie and "HttpOnly" in cookie and "samesite=lax" in cookie.lower()
    user = await db.scalar(select(User).where(User.google_sub == "google-sub-123"))
    assert user is not None and user.email == "new.user@gmail.com" and user.last_login_at is not None


async def test_google_login_is_an_upsert(client, google_ok, db):
    await client.post("/api/auth/google", json={"credential": "x" * 40})
    await client.post("/api/auth/google", json={"credential": "x" * 40})
    users = (await db.scalars(select(User).where(User.google_sub == "google-sub-123"))).all()
    assert len(users) == 1


async def test_invalid_google_token_is_rejected(client, monkeypatch):
    async def bad(credential: str):
        raise GoogleAuthError("Google email is not verified")

    monkeypatch.setattr("app.routers.auth.verify_google_token", bad)
    resp = await client.post("/api/auth/google", json={"credential": "x" * 40})
    assert resp.status_code == 401


async def test_verify_rejects_unverified_email_and_wrong_audience(monkeypatch, settings):
    from app.services import google_auth

    settings.google_client_id = "test-client-id"
    for claims in (
        {**CLAIMS, "email_verified": False},
        {**CLAIMS, "aud": "someone-else"},
    ):
        monkeypatch.setattr(google_auth, "_verify_sync", lambda cred, cid, c=claims: c)
        with pytest.raises(GoogleAuthError):
            await google_auth.verify_google_token("token")


async def test_admin_email_becomes_admin(client, google_ok, settings):
    settings.admin_emails = "someone@x.com, NEW.USER@gmail.com"
    resp = await client.post("/api/auth/google", json={"credential": "x" * 40})
    assert resp.json()["user"]["role"] == "admin"
    assert resp.json()["redirect"] == "/admin"


async def test_me_requires_session_and_logout_clears_it(client, db):
    assert (await client.get("/api/auth/me")).status_code == 401
    user = await make_user(db, email="p@x.com", role="patient")
    login(client, user)
    me = await client.get("/api/auth/me")
    assert me.status_code == 200 and me.json()["email"] == "p@x.com"
    out = await client.post("/api/auth/logout")
    assert out.status_code == 204
    assert 'ht_session=""' in out.headers["set-cookie"] or "Max-Age=0" in out.headers["set-cookie"]


async def test_csrf_header_required_for_state_changes(client, db):
    user = await make_user(db, email="p@x.com", role="patient")
    login(client, user)
    resp = await client.post("/api/auth/logout", headers={"X-HT-Request": ""})
    assert resp.status_code == 403


async def test_demo_login_404_when_demo_mode_off(client, settings):
    settings.demo_mode = False
    resp = await client.post("/api/auth/demo", json={"persona": "priya"})
    assert resp.status_code == 404


async def test_demo_login_issues_session_for_persona(client, settings, fhir):
    settings.demo_mode = True
    resp = await client.post("/api/auth/demo", json={"persona": "meena"})
    assert resp.status_code == 200
    assert resp.json()["redirect"] == "/doctor"
    assert resp.json()["user"]["doctor"]["verification_status"] == "verified"
    assert fhir.store["Practitioner"]  # verified persona has a Practitioner
    me = await client.get("/api/auth/me")
    assert me.json()["name"] == "Dr. Meena Raghavan"


async def test_patient_onboarding_creates_profile_and_fhir_patient(client, db, fhir):
    user = await make_user(db, email="priya@x.com")
    login(client, user)
    resp = await client.post(
        "/api/onboarding/patient",
        json={
            "name": "Priya Rajan",
            "profile": {
                "display_name": "Rajan Subramanian",
                "relationship": "parent",
                "dob": "1962-05-14",
                "sex": "male",
                "blood_group": "B+",
                "emergency_contact_name": "Priya Rajan",
                "emergency_contact_phone": "+91 98400 12345",
            },
        },
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["redirect"] == "/app"
    profile = await db.scalar(select(HealthProfile).where(HealthProfile.owner_user_id == user.id))
    assert profile is not None
    assert re.fullmatch(r"HT-[2-9A-HJKMNP-Z]{4}-[2-9A-HJKMNP-Z]{4}", profile.healththread_id)
    patient = fhir.store["Patient"][profile.fhir_patient_id]
    assert patient["birthDate"] == "1962-05-14"
    assert patient["identifier"][0]["value"] == profile.healththread_id
    # Profiles list
    login(client, (await db.get(User, user.id)))
    profiles = (await client.get("/api/profiles")).json()
    assert [p["display_name"] for p in profiles] == ["Rajan Subramanian"]
    assert profiles[0]["age"] >= 64


async def test_onboarding_twice_is_rejected(client, db):
    user = await make_user(db, email="p@x.com", role="patient")
    login(client, user)
    resp = await client.post(
        "/api/onboarding/doctor",
        json={
            "full_name": "Dr X",
            "specialty": "Nephrology",
            "organization": "Hospital",
            "council": "Council",
            "registration_number": "AB-1234",
        },
    )
    assert resp.status_code == 409


async def test_doctor_onboarding_is_pending_and_notifies_admins(client, db):
    admin = await make_user(db, email="admin@x.com", role="admin")
    user = await make_user(db, email="doc@x.com")
    login(client, user)
    bad = await client.post(
        "/api/onboarding/doctor",
        json={
            "full_name": "Dr Arjun Mehta",
            "specialty": "Astrology",
            "organization": "Clinic",
            "council": "Maharashtra Medical Council",
            "registration_number": "??",
        },
    )
    assert bad.status_code == 422
    resp = await client.post(
        "/api/onboarding/doctor",
        json={
            "full_name": "Dr Arjun Mehta",
            "specialty": "General Medicine",
            "organization": "Clinic",
            "council": "Maharashtra Medical Council",
            "registration_number": "mmc-20417",
        },
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["user"]["doctor"]["verification_status"] == "pending"
    assert resp.json()["user"]["doctor"]["registration_number"] == "MMC-20417"
    notes = (await db.scalars(select(Notification).where(Notification.user_id == admin.id))).all()
    assert len(notes) == 1


async def test_unverified_doctor_sees_no_patient_data(client, db):
    doc = await make_user(db, email="doc@x.com", role="doctor", doctor_status="pending")
    login(client, doc)
    assert (await client.get("/api/doctor/patients")).status_code == 403


async def test_admin_verifies_doctor_and_creates_practitioner(client, db, fhir):
    admin = await make_user(db, email="admin@x.com", role="admin")
    doc = await make_user(db, email="doc@x.com", role="doctor", doctor_status="pending", name="Dr Meena")
    login(client, admin)
    pending = (await client.get("/api/admin/doctors")).json()
    assert [d["email"] for d in pending] == ["doc@x.com"]
    reject_without_note = await client.post(
        f"/api/admin/doctors/{doc.id}/verify", json={"decision": "reject"}
    )
    assert reject_without_note.status_code == 422
    resp = await client.post(f"/api/admin/doctors/{doc.id}/verify", json={"decision": "approve"})
    assert resp.status_code == 200 and resp.json()["verification_status"] == "verified"
    dp = await db.get(DoctorProfile, doc.id)
    await db.refresh(dp)
    assert dp.fhir_practitioner_id in fhir.store["Practitioner"]
    # The doctor can now use doctor endpoints.
    login(client, doc)
    assert (await client.get("/api/doctor/patients")).status_code == 200


async def test_admin_cannot_open_patient_profiles(client, db):
    owner = await make_user(db, email="p@x.com", role="patient")
    admin = await make_user(db, email="admin@x.com", role="admin")
    login(client, owner)
    created = await client.post(
        "/api/profiles",
        json={"display_name": "Lakshmi Iyer", "relationship": "self", "dob": "1968-02-01", "sex": "female"},
    )
    assert created.status_code == 201
    login(client, admin)
    assert (await client.get(f"/api/profiles/{created.json()['id']}")).status_code == 403
    assert (await client.get("/api/profiles")).status_code == 403
    assert (await client.get("/api/doctor/patients")).status_code == 403


async def test_patient_cannot_use_admin_endpoints(client, db):
    owner = await make_user(db, email="p@x.com", role="patient")
    login(client, owner)
    assert (await client.get("/api/admin/doctors")).status_code == 403
    assert (await client.get("/api/admin/stats")).status_code == 403
