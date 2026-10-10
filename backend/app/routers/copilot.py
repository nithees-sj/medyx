"""Clinical copilot: per-patient chat (SSE), specialty summary, and panel insights."""

import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.client import AIError
from app.db import get_db
from app.deps import client_ip, current_user, require_verified_doctor
from app.models import Alert, ChatMessage, User
from app.rate_limit import AI_LIMIT, limiter
from app.routers.alerts import visible_to
from app.services.audit import log_event
from app.services.consent import Access, get_scoped_record
from app.services.copilot import chat, insights, summary
from app.services.copilot.digest import Digest, build_digest
from app.services.record import PatientRecord
from app.services.safety.engine import today

router = APIRouter(tags=["copilot"])


async def scoped_digest(db: AsyncSession, profile_id: uuid.UUID, user: User) -> tuple[Access, PatientRecord, Digest]:
    """The digest is built from get_scoped_record() output only (spec §9.1, §16)."""
    access, record = await get_scoped_record(db, profile_id, user)
    alerts = (await db.scalars(select(Alert).where(Alert.profile_id == profile_id, Alert.status == "active"))).all()
    alerts = [a for a in alerts if not (a.details or {}).get("superseded_by") and visible_to(record, a)]
    return access, record, build_digest(record, access.scopes, list(alerts), today())


def _doctor_only(access: Access) -> None:
    if access.is_owner:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "The copilot is for the doctors you share with")


class ChatIn(BaseModel):
    message: str = Field(min_length=1, max_length=4000)


@router.get("/profiles/{profile_id}/chat")
async def chat_history(
    profile_id: uuid.UUID, user: User = Depends(current_user), db: AsyncSession = Depends(get_db)
) -> list[dict[str, Any]]:
    access, _ = await get_scoped_record(db, profile_id, user)
    _doctor_only(access)
    rows = (
        await db.scalars(
            select(ChatMessage)
            .where(ChatMessage.profile_id == profile_id, ChatMessage.doctor_user_id == user.id)
            .order_by(ChatMessage.created_at)
        )
    ).all()
    return [
        {
            "id": str(m.id),
            "role": m.role,
            "content": m.content,
            "citations": m.citations,
            "created_at": m.created_at.isoformat(),
        }
        for m in rows
    ]


@router.post("/profiles/{profile_id}/chat")
@limiter.limit(AI_LIMIT)
async def chat_stream(
    profile_id: uuid.UUID,
    body: ChatIn,
    request: Request,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
) -> StreamingResponse:
    access, _, digest = await scoped_digest(db, profile_id, user)
    _doctor_only(access)
    await log_event(
        db,
        profile_id=profile_id,
        actor_user_id=user.id,
        actor_label=access.actor_label,
        action="chat",
        scopes=sorted(access.scopes),
        details={"question_chars": len(body.message)},
        ip=client_ip(request),
    )
    await db.commit()
    return StreamingResponse(
        chat.stream_answer(profile_id=profile_id, doctor_id=user.id, question=body.message, digest=digest),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache, no-transform", "X-Accel-Buffering": "no"},
    )


@router.get("/profiles/{profile_id}/summary")
@limiter.limit(AI_LIMIT)
async def specialty_summary(
    profile_id: uuid.UUID,
    request: Request,
    specialty: str = "General Medicine",
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    access, record, digest = await scoped_digest(db, profile_id, user)
    try:
        content, cached = await summary.get_summary(
            db,
            profile_id=profile_id,
            specialty=specialty[:100],
            scope_key=",".join(sorted(access.scopes)),
            record_version=record.version,
            digest=digest,
        )
    except AIError as e:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(e)) from e
    if not access.is_owner:
        await log_event(
            db,
            profile_id=profile_id,
            actor_user_id=user.id,
            actor_label=access.actor_label,
            action="summary",
            scopes=sorted(access.scopes),
            details={"specialty": specialty, "cached": cached},
            ip=client_ip(request),
        )
        await db.commit()
    return {"specialty": specialty, "record_version": record.version, "cached": cached, "sections": content}


class InsightsIn(BaseModel):
    question: str = Field(min_length=3, max_length=500)


@router.post("/doctor/insights")
@limiter.limit(AI_LIMIT)
async def panel_insights(
    body: InsightsIn,
    request: Request,
    doctor: User = Depends(require_verified_doctor),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    try:
        result = await insights.answer(db, doctor, body.question)
    except AIError as e:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(e)) from e
    dp = doctor.doctor_profile
    label = f"{dp.full_name} ({dp.specialty})" if dp else doctor.name
    for pid in result["touched_profiles"]:
        await log_event(
            db,
            profile_id=uuid.UUID(pid),
            actor_user_id=doctor.id,
            actor_label=label,
            action="view",
            scopes=["labs"],
            details={"section": "panel insights", "question": body.question[:200]},
            ip=client_ip(request),
        )
    await db.commit()
    result.pop("touched_profiles")
    return result
