import re
import uuid
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator

SPECIALTIES = [
    "General Medicine",
    "Family Medicine",
    "Nephrology",
    "Cardiology",
    "Endocrinology & Diabetology",
    "Internal Medicine",
    "Pulmonology",
    "Gastroenterology",
    "Neurology",
    "Psychiatry",
    "Paediatrics",
    "Obstetrics & Gynaecology",
    "Orthopaedics",
    "Dermatology",
    "Emergency Medicine",
]

_REG_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9/\- ]{3,23}$")


class GoogleLoginIn(BaseModel):
    credential: str = Field(min_length=20)


class DemoLoginIn(BaseModel):
    persona: Literal["priya", "meena", "arjun", "admin"]


class DoctorOut(BaseModel):
    full_name: str
    specialty: str
    organization: str
    council: str
    registration_number: str
    verification_status: str
    review_note: str | None = None
    verified_at: datetime | None = None


class MeOut(BaseModel):
    id: uuid.UUID
    email: str
    name: str
    avatar_url: str | None
    role: str | None
    onboarded: bool
    doctor: DoctorOut | None = None


class LoginOut(BaseModel):
    user: MeOut
    redirect: str


class AuthConfigOut(BaseModel):
    demo_mode: bool
    google_client_id: str | None
    personas: list[dict[str, str]]
    specialties: list[str]


class ProfileIn(BaseModel):
    display_name: str = Field(min_length=2, max_length=200)
    relationship: Literal["self", "parent", "child", "spouse", "other"]
    dob: date
    sex: Literal["male", "female", "other", "unknown"]
    blood_group: Literal["A+", "A-", "B+", "B-", "AB+", "AB-", "O+", "O-", "unknown"] = "unknown"
    emergency_contact_name: str | None = Field(default=None, max_length=200)
    emergency_contact_phone: str | None = Field(default=None, max_length=40)

    @field_validator("dob")
    @classmethod
    def _dob_in_past(cls, v: date) -> date:
        if v > date.today() or v.year < 1900:
            raise ValueError("Date of birth must be in the past")
        return v

    @field_validator("emergency_contact_phone")
    @classmethod
    def _phone(cls, v: str | None) -> str | None:
        if v and not re.fullmatch(r"\+?[0-9 ()-]{6,20}", v):
            raise ValueError("Enter a valid phone number")
        return v or None


class PatientOnboardingIn(BaseModel):
    name: str = Field(min_length=2, max_length=200)
    profile: ProfileIn


class DoctorOnboardingIn(BaseModel):
    full_name: str = Field(min_length=3, max_length=200)
    specialty: str
    organization: str = Field(min_length=2, max_length=200)
    council: str = Field(min_length=3, max_length=200)
    registration_number: str

    @field_validator("specialty")
    @classmethod
    def _specialty(cls, v: str) -> str:
        if v not in SPECIALTIES:
            raise ValueError("Choose a specialty from the list")
        return v

    @field_validator("registration_number")
    @classmethod
    def _reg(cls, v: str) -> str:
        v = v.strip().upper()
        if not _REG_RE.fullmatch(v) or not any(c.isdigit() for c in v):
            raise ValueError("Registration number should look like TNMC-58213 or 2004/02/1234")
        return v
