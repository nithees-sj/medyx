"""Specialty-tailored pre-visit summary, cached per (profile, specialty, scopes, record_version)."""

from typing import Literal

from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai import client as ai
from app.models import SummaryCache
from app.services.copilot.digest import Digest


class Line(BaseModel):
    text: str
    citations: list[str] = Field(description="Citation keys copied from the RECORD, e.g. Observation/1248")


class LabLine(Line):
    trend: Literal["up", "down", "stable", "single"]


class Summary(BaseModel):
    key_problems: list[Line]
    current_medications: list[Line]
    relevant_labs: list[LabLine]
    active_alerts: list[Line]
    open_questions: list[Line]


def _clean(summary: Summary, digest: Digest) -> dict:
    """Keep only citations that exist in the digest; attach chip data for the UI."""
    out: dict = {}
    for section, lines in summary.model_dump().items():
        cleaned = []
        for line in lines:
            keys = [k.strip("[] ") for k in line["citations"]]
            chips = [{"key": k, **digest.index[k]} for k in keys if digest.known(k)]
            cleaned.append({**line, "citations": chips, "uncited": not chips})
        out[section] = cleaned
    return out


async def get_summary(
    db: AsyncSession, *, profile_id, specialty: str, scope_key: str, record_version: int, digest: Digest
) -> tuple[dict, bool]:
    """Returns (summary, cached?)."""
    cached = await db.get(SummaryCache, (profile_id, specialty, scope_key))
    if cached and cached.record_version == record_version:
        return cached.content, True
    result = await ai.generate_structured(
        purpose="summary",
        system=ai.load_prompt("summary").replace("{specialty}", specialty).replace("{digest}", digest.text),
        contents=[f"Write the {specialty} pre-visit summary."],
        schema=Summary,
        thinking="low",
        temperature=0.1,
        max_quota_wait=30,
    )
    content = _clean(result, digest)
    if cached:
        cached.record_version, cached.content = record_version, content
    else:
        db.add(
            SummaryCache(
                profile_id=profile_id,
                specialty=specialty,
                scope_key=scope_key,
                record_version=record_version,
                content=content,
            )
        )
    await db.commit()
    return content, False
