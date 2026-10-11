"""FastAPI dependencies: authentication and role guards."""

import uuid
from collections.abc import Awaitable, Callable

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.models import User
from app.security import SESSION_COOKIE, decode_session_token


async def optional_user(request: Request, db: AsyncSession = Depends(get_db)) -> User | None:
    token = request.cookies.get(SESSION_COOKIE)
    if not token:
        return None
    payload = decode_session_token(token)
    if not payload:
        return None
    try:
        user_id = uuid.UUID(payload["user_id"])
    except (KeyError, ValueError):
        return None
    # Always reload from the DB: role and verification can change after the cookie was issued.
    user = await db.get(User, user_id)
    if user is not None:
        # Read by the request-telemetry middleware (who made this call).
        request.state.user_id = user.id
        request.state.role = user.role
    return user


async def current_user(user: User | None = Depends(optional_user)) -> User:
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not signed in")
    return user


def require_role(*roles: str) -> Callable[..., Awaitable[User]]:
    async def dep(user: User = Depends(current_user)) -> User:
        if user.role not in roles:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Not allowed for your role")
        return user

    return dep


require_patient = require_role("patient")
require_admin = require_role("admin")
require_doctor = require_role("doctor")


async def require_verified_doctor(user: User = Depends(require_doctor)) -> User:
    if not user.doctor_profile or not user.doctor_profile.is_verified:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Doctor account is awaiting verification")
    return user


def client_ip(request: Request) -> str | None:
    return request.client.host if request.client else None
