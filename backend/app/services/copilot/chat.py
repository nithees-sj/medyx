"""Doctor ↔ copilot chat over one patient's scoped record (SSE streaming)."""

import json
import logging
import uuid
from collections.abc import AsyncIterator
from typing import Any

from google.genai import types
from sqlalchemy import select

from app.ai import client as ai
from app.db import SessionLocal
from app.models import ChatMessage
from app.services.copilot.digest import Digest, extract_citations

log = logging.getLogger(__name__)
HISTORY_TURNS = 12


def sse(event: dict[str, Any]) -> str:
    return f"data: {json.dumps(event, ensure_ascii=False)}\n\n"


async def history(profile_id: uuid.UUID, doctor_id: uuid.UUID) -> list[ChatMessage]:
    async with SessionLocal() as db:
        rows = (
            await db.scalars(
                select(ChatMessage)
                .where(ChatMessage.profile_id == profile_id, ChatMessage.doctor_user_id == doctor_id)
                .order_by(ChatMessage.created_at.desc())
                .limit(HISTORY_TURNS)
            )
        ).all()
    return list(reversed(rows))


async def stream_answer(
    *, profile_id: uuid.UUID, doctor_id: uuid.UUID, question: str, digest: Digest
) -> AsyncIterator[str]:
    """Yields SSE lines: {type: delta}, then {type: done, citations} or {type: error}."""
    past = await history(profile_id, doctor_id)
    contents: list[types.Content] = [
        types.Content(role="user" if m.role == "user" else "model", parts=[types.Part.from_text(text=m.content)])
        for m in past
    ]
    contents.append(types.Content(role="user", parts=[types.Part.from_text(text=question)]))
    async with SessionLocal() as db:
        db.add(ChatMessage(profile_id=profile_id, doctor_user_id=doctor_id, role="user", content=question))
        await db.commit()

    system = ai.load_prompt("chat").replace("{digest}", digest.text)
    answer = ""
    try:
        async for chunk in ai.stream_text(purpose="chat", system=system, contents=contents, thinking="low"):
            answer += chunk
            yield sse({"type": "delta", "text": chunk})
    except ai.AIError as e:
        yield sse({"type": "error", "message": str(e)})
        return

    citations, unknown = extract_citations(answer, digest)
    if unknown:
        log.warning("chat answer cited %d unknown keys", len(unknown))
    async with SessionLocal() as db:
        msg = ChatMessage(
            profile_id=profile_id,
            doctor_user_id=doctor_id,
            role="assistant",
            content=answer,
            citations=citations + [{"key": k, "unknown": True} for k in unknown],
        )
        db.add(msg)
        await db.commit()
        yield sse({"type": "done", "message_id": str(msg.id), "citations": msg.citations, "uncited": not citations})
