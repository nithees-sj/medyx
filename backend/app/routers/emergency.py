"""Emergency card: owner controls (enable, regenerate, disable, print) and the public view."""

import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db import get_db, utcnow
from app.deps import client_ip
from app.models import EmergencyCard, HealthProfile
from app.rate_limit import EMERGENCY_LIMIT, limiter
from app.security import hash_token, new_secret_token
from app.services.audit import log_event
from app.services.consent import Access, owner_access
from app.services.emergency_card import card_data, lockscreen_png, wallet_pdf
from app.services.notifications import notify
from app.services.record import load_record
from app.services.safety.engine import today

router = APIRouter(tags=["emergency"])


def card_url(token: str) -> str:
    return f"{get_settings().app_base_url.rstrip('/')}/emergency/{token}"


async def _card(db: AsyncSession, profile_id: uuid.UUID) -> EmergencyCard | None:
    return await db.get(EmergencyCard, profile_id)


@router.get("/profiles/{profile_id}/emergency")
async def emergency_status(
    profile_id: uuid.UUID, access: Access = Depends(owner_access), db: AsyncSession = Depends(get_db)
) -> dict[str, Any]:
    card = await _card(db, profile_id)
    record = await load_record(db, access.profile)
    return {
        "enabled": bool(card and card.enabled),
        "created_at": card.created_at.isoformat() if card else None,
        "regenerated_at": card.regenerated_at.isoformat() if card and card.regenerated_at else None,
        "preview": card_data(record, access.profile, today()),
    }


@router.post("/profiles/{profile_id}/emergency/enable")
async def enable_card(
    profile_id: uuid.UUID, access: Access = Depends(owner_access), db: AsyncSession = Depends(get_db)
) -> dict[str, Any]:
    """Create (or regenerate) the card token. The token is only shown now; we store its hash."""
    token = new_secret_token()
    card = await _card(db, profile_id)
    if card is None:
        card = EmergencyCard(profile_id=profile_id, token_hash=hash_token(token), enabled=True)
        db.add(card)
    else:
        card.token_hash = hash_token(token)  # the old QR stops working immediately
        card.enabled = True
        card.regenerated_at = utcnow()
    await db.commit()
    return {"token": token, "url": card_url(token), "enabled": True}


@router.post("/profiles/{profile_id}/emergency/disable")
async def disable_card(
    profile_id: uuid.UUID, access: Access = Depends(owner_access), db: AsyncSession = Depends(get_db)
) -> dict[str, Any]:
    card = await _card(db, profile_id)
    if card:
        card.enabled = False
        card.token_hash = hash_token(new_secret_token())  # invalidate the printed QR too
        await db.commit()
    return {"enabled": False}


class TokenIn(BaseModel):
    token: str


async def _verified_card(db: AsyncSession, access: Access, token: str) -> dict[str, Any]:
    card = await _card(db, access.profile.id)
    if not card or not card.enabled or card.token_hash != hash_token(token):
        raise HTTPException(status.HTTP_409_CONFLICT, "This card was regenerated or disabled. Create a new one.")
    record = await load_record(db, access.profile)
    return card_data(record, access.profile, today())


@router.post("/profiles/{profile_id}/emergency/wallet.pdf")
async def wallet_card(
    profile_id: uuid.UUID, body: TokenIn, access: Access = Depends(owner_access), db: AsyncSession = Depends(get_db)
) -> Response:
    data = await _verified_card(db, access, body.token)
    pdf = wallet_pdf(data, card_url(body.token))
    return Response(
        pdf,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="emergency-card-{data["healththread_id"]}.pdf"'},
    )


@router.post("/profiles/{profile_id}/emergency/lockscreen.png")
async def lockscreen(
    profile_id: uuid.UUID, body: TokenIn, access: Access = Depends(owner_access), db: AsyncSession = Depends(get_db)
) -> Response:
    data = await _verified_card(db, access, body.token)
    png = lockscreen_png(data, card_url(body.token))
    return Response(
        png,
        media_type="image/png",
        headers={"Content-Disposition": f'attachment; filename="emergency-lockscreen-{data["healththread_id"]}.png"'},
    )


@router.get("/emergency/{token}")
@limiter.limit(EMERGENCY_LIMIT)
async def public_card(token: str, request: Request, db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    """Public, no login. Every view is audited and the owner is notified."""
    card = await db.scalar(select(EmergencyCard).where(EmergencyCard.token_hash == hash_token(token)))
    if card is None or not card.enabled:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "This emergency card is not active")
    profile = await db.get(HealthProfile, card.profile_id)
    assert profile is not None
    record = await load_record(db, profile)
    data = card_data(record, profile, today())
    data["last_updated"] = max(
        [profile.created_at.isoformat()] + [d.created_at for d in record.documents]  # documents' upload instants
    )
    ip = client_ip(request)
    await log_event(
        db,
        profile_id=profile.id,
        actor_user_id=None,
        actor_label="Emergency access (no login)",
        action="emergency_view",
        scopes=["allergies", "medications", "conditions"],
        details={"user_agent": (request.headers.get("user-agent") or "")[:200]},
        ip=ip,
    )
    from zoneinfo import ZoneInfo

    local = utcnow().astimezone(ZoneInfo(get_settings().default_timezone))
    await notify(
        db,
        profile.owner_user_id,
        "emergency_view",
        f"Emergency access to {profile.display_name.split()[0]}'s card at {local.strftime('%-I:%M %p')}",
        "Someone scanned the emergency card. If this wasn't expected, regenerate the card.",
        f"/app/p/{profile.id}/access-log",
    )
    await db.commit()
    return data
