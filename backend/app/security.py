"""Session tokens, cookies and secret-token helpers."""

import hashlib
import secrets
from datetime import timedelta
from typing import Any

import jwt
from fastapi import Response

from app.config import get_settings
from app.db import utcnow

SESSION_COOKIE = "ht_session"
CSRF_HEADER = "X-HT-Request"


def create_session_token(user_id: str, role: str | None, onboarded: bool) -> str:
    s = get_settings()
    now = utcnow()
    payload = {
        "user_id": user_id,
        "role": role,
        "onboarded": onboarded,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(hours=s.jwt_expiry_hours)).timestamp()),
    }
    return jwt.encode(payload, s.jwt_secret, algorithm="HS256")


def decode_session_token(token: str) -> dict[str, Any] | None:
    try:
        return jwt.decode(token, get_settings().jwt_secret, algorithms=["HS256"])
    except jwt.PyJWTError:
        return None


def set_session_cookie(response: Response, user_id: str, role: str | None, onboarded: bool) -> None:
    s = get_settings()
    response.set_cookie(
        SESSION_COOKIE,
        create_session_token(user_id, role, onboarded),
        max_age=s.jwt_expiry_hours * 3600,
        httponly=True,
        samesite="lax",
        secure=s.cookie_secure,
        path="/",
    )


def clear_session_cookie(response: Response) -> None:
    response.delete_cookie(SESSION_COOKIE, path="/", samesite="lax", secure=get_settings().cookie_secure)


def new_secret_token() -> str:
    """32 random bytes, URL-safe. Only its hash is ever stored."""
    return secrets.token_urlsafe(32)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()
