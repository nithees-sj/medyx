import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from app.config import get_settings
from app.middleware import CSRFHeaderMiddleware, RequestTelemetryMiddleware
from app.rate_limit import limiter
from app.routers import (
    admin,
    alerts,
    auth,
    clinical,
    consents,
    copilot,
    doctor,
    documents,
    emergency,
    health,
    monitoring,
    notifications,
    onboarding,
    profiles,
    record,
    review,
    verification,
)
from app.services import telemetry
from app.services.fhir_client import get_fhir
from app.services.ingest.pipeline import post_write_hooks, worker
from app.services.safety.engine import safety_hook

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


async def _expire_consents() -> str:
    """Expiry is checked on every request; this also tidies up statuses in the background."""
    from app.db import SessionLocal
    from app.routers.consents import expire_stale

    async with SessionLocal() as db:
        await expire_stale(db)
    return "ok"


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    from app.services.verification.service import recheck_due

    get_settings().storage_dir.mkdir(parents=True, exist_ok=True)
    await worker.start()
    background = [
        asyncio.create_task(telemetry.flush_forever()),
        asyncio.create_task(telemetry.every("consent expiry", 300, _expire_consents)),
        asyncio.create_task(telemetry.every("doctor re-check", 6 * 3600, recheck_due, initial_delay=60)),
        asyncio.create_task(telemetry.every("telemetry retention", 12 * 3600, telemetry.purge_old, initial_delay=120)),
    ]
    telemetry.event("app_started", "API server started")
    yield
    for task in background:
        task.cancel()
    await telemetry.flush()
    await worker.stop()
    await get_fhir().aclose()


def create_app() -> FastAPI:
    settings = get_settings()
    if safety_hook not in post_write_hooks:
        post_write_hooks.append(safety_hook)
    app = FastAPI(title="HealthThread API", lifespan=lifespan)
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)  # type: ignore[arg-type]
    app.add_middleware(CSRFHeaderMiddleware)
    # Added last = outermost: also sees the CSRF middleware's 403s.
    app.add_middleware(RequestTelemetryMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[settings.app_base_url],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    for r in (
        health,
        auth,
        onboarding,
        profiles,
        documents,
        review,
        record,
        alerts,
        clinical,
        copilot,
        consents,
        emergency,
        admin,
        monitoring,
        verification,
        notifications,
        doctor,
    ):
        app.include_router(r.router, prefix="/api")
    return app


app = create_app()
