import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db, utcnow
from app.deps import current_user
from app.models import Notification, User

router = APIRouter(prefix="/notifications", tags=["notifications"])


class NotificationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    type: str
    title: str
    body: str | None
    link: str | None
    read_at: datetime | None
    created_at: datetime


class NotificationsOut(BaseModel):
    unread: int
    items: list[NotificationOut]


@router.get("", response_model=NotificationsOut)
async def list_notifications(user: User = Depends(current_user), db: AsyncSession = Depends(get_db)) -> dict:
    items = (
        await db.scalars(
            select(Notification)
            .where(Notification.user_id == user.id)
            .order_by(Notification.created_at.desc())
            .limit(30)
        )
    ).all()
    unread = await db.scalar(
        select(func.count()).where(Notification.user_id == user.id, Notification.read_at.is_(None))
    )
    return {"unread": unread or 0, "items": items}


@router.post("/{notification_id}/read", status_code=204)
async def mark_read(
    notification_id: uuid.UUID, user: User = Depends(current_user), db: AsyncSession = Depends(get_db)
) -> None:
    n = await db.get(Notification, notification_id)
    if n is None or n.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Notification not found")
    n.read_at = n.read_at or utcnow()
    await db.commit()


@router.post("/read-all", status_code=204)
async def mark_all_read(user: User = Depends(current_user), db: AsyncSession = Depends(get_db)) -> None:
    await db.execute(
        update(Notification)
        .where(Notification.user_id == user.id, Notification.read_at.is_(None))
        .values(read_at=utcnow())
    )
    await db.commit()
