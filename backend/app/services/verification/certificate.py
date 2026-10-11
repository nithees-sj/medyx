"""Reading a doctor's uploaded registration certificate with Gemini.

The extracted fields are *evidence for a reviewer*, compared against what the doctor typed by
deterministic rules (matching.py). Reading a document cannot prove it is genuine, so a
certificate alone never approves anyone.
"""

from datetime import date
from typing import Literal

from pydantic import BaseModel, Field

from app.ai import client as ai


class CertificateFields(BaseModel):
    document_type: Literal["registration_certificate", "degree_certificate", "id_card", "other"]
    issuer: str | None = None
    full_name: str | None = None
    registration_number: str | None = None
    council: str | None = None
    registration_date: date | None = None
    qualification: str | None = None
    confidence: float = Field(ge=0, le=1)
    concerns: list[str] = Field(default_factory=list, max_length=8)


async def read_certificate(data: bytes, mime: str) -> CertificateFields:
    return await ai.generate_structured(
        purpose="verify_certificate",
        system=ai.load_prompt("doctor_certificate"),
        contents=[ai.file_part(data, mime), "Read this document into the schema."],
        schema=CertificateFields,
        thinking="low",
        max_quota_wait=60,
    )
