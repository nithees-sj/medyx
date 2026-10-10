from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db import get_db, utcnow
from app.deps import current_user
from app.models import User
from app.rate_limit import AUTH_LIMIT, limiter
from app.schemas.auth import (
    SPECIALTIES,
    AuthConfigOut,
    DemoLoginIn,
    DoctorOut,
    GoogleLoginIn,
    LoginOut,
    MeOut,
)
from app.security import clear_session_cookie, set_session_cookie
from app.services.demo import PERSONAS, ensure_persona
from app.services.google_auth import GoogleAuthError, verify_google_token

router = APIRouter(prefix="/auth", tags=["auth"])


def home_for(user: User) -> str:
    return {"patient": "/app", "doctor": "/doctor", "admin": "/admin"}.get(user.role or "", "/onboarding")


def me_out(user: User) -> MeOut:
    dp = user.doctor_profile
    return MeOut(
        id=user.id,
        email=user.email,
        name=user.name,
        avatar_url=user.avatar_url,
        role=user.role,
        onboarded=user.onboarded,
        doctor=DoctorOut.model_validate(dp, from_attributes=True) if dp else None,
    )


def start_session(response: Response, user: User) -> LoginOut:
    set_session_cookie(response, str(user.id), user.role, user.onboarded)
    return LoginOut(user=me_out(user), redirect=home_for(user))


@router.get("/config", response_model=AuthConfigOut)
async def auth_config() -> AuthConfigOut:
    s = get_settings()
    return AuthConfigOut(
        demo_mode=s.demo_mode,
        google_client_id=s.google_client_id or None,
        personas=[{"key": p.key, "label": p.label} for p in PERSONAS.values()] if s.demo_mode else [],
        specialties=SPECIALTIES,
    )


@router.post("/google", response_model=LoginOut)
@limiter.limit(AUTH_LIMIT)
async def google_login(
    request: Request, body: GoogleLoginIn, response: Response, db: AsyncSession = Depends(get_db)
) -> LoginOut:
    try:
        claims = await verify_google_token(body.credential)
    except GoogleAuthError as e:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, str(e)) from e

    user = await db.scalar(select(User).where(User.google_sub == claims["sub"]))
    if user is None:
        user = User(
            google_sub=claims["sub"], email=claims["email"], name=claims.get("name") or claims["email"]
        )
        db.add(user)
    user.email = claims["email"]
    user.avatar_url = claims.get("picture")
    if claims.get("name") and not user.onboarded:
        user.name = claims["name"]
    if user.role is None and claims["email"].lower() in get_settings().admin_email_set:
        user.role = "admin"
    user.last_login_at = utcnow()
    await db.commit()
    await db.refresh(user)
    return start_session(response, user)


@router.post("/demo", response_model=LoginOut)
@limiter.limit(AUTH_LIMIT)
async def demo_login(
    request: Request, body: DemoLoginIn, response: Response, db: AsyncSession = Depends(get_db)
) -> LoginOut:
    if not get_settings().demo_mode:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Not Found")
    user = await ensure_persona(db, body.persona)
    user.last_login_at = utcnow()
    await db.commit()
    await db.refresh(user)
    return start_session(response, user)


@router.get("/me", response_model=MeOut)
async def me(user: User = Depends(current_user)) -> MeOut:
    return me_out(user)


@router.post("/logout", status_code=204)
async def logout(response: Response) -> Response:
    clear_session_cookie(response)
    response.status_code = 204
    return response
