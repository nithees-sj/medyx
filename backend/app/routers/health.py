from fastapi import APIRouter
from sqlalchemy import text

from app.config import get_settings
from app.db import SessionLocal
from app.services.fhir_client import get_fhir

router = APIRouter(tags=["health"])


@router.get("/health")
async def health() -> dict:
    db_ok = fhir_ok = False
    fhir_version = None
    try:
        async with SessionLocal() as session:
            await session.execute(text("SELECT 1"))
        db_ok = True
    except Exception:
        pass
    try:
        meta = await get_fhir().metadata()
        fhir_ok = meta.get("resourceType") == "CapabilityStatement"
        fhir_version = meta.get("fhirVersion")
    except Exception:
        pass
    settings = get_settings()
    return {
        "status": "ok" if db_ok and fhir_ok else "degraded",
        "database": db_ok,
        "fhir": fhir_ok,
        "fhir_version": fhir_version,
        "demo_mode": settings.demo_mode,
        "ai_configured": bool(settings.gemini_api_key),
    }
