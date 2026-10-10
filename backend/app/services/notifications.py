import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Notification, User


async def notify(
    db: AsyncSession,
    user_id: uuid.UUID,
    type: str,
    title: str,
    body: str | None = None,
    link: str | None = None,
) -> Notification:
    n = Notification(user_id=user_id, type=type, title=title, body=body, link=link)
    db.add(n)
    await db.flush()
    return n


async def notify_admins(db: AsyncSession, type: str, title: str, body: str | None, link: str | None) -> None:
    admin_ids = (await db.scalars(select(User.id).where(User.role == "admin"))).all()
    for uid in admin_ids:
        await notify(db, uid, type, title, body, link)
