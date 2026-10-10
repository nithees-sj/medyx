import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from app.config import get_settings
from app.middleware import CSRFHeaderMiddleware
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
    notifications,
    onboarding,
    profiles,
    record,
    review,
)
from app.services.fhir_client import get_fhir
from app.services.ingest.pipeline import post_write_hooks, worker
from app.services.safety.engine import safety_hook

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


async def _expire_consents_periodically() -> None:
    """Expiry is checked on every request; this also tidies up statuses in the background."""
    from app.db import SessionLocal
    from app.routers.consents import expire_stale

    while True:
        try:
            async with SessionLocal() as db:
                await expire_stale(db)
        except Exception:
            logging.getLogger(__name__).exception("consent cleanup failed")
        await asyncio.sleep(300)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    get_settings().storage_dir.mkdir(parents=True, exist_ok=True)
    await worker.start()
    cleanup = asyncio.create_task(_expire_consents_periodically())
    yield
    cleanup.cancel()
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
        notifications,
        doctor,
    ):
        app.include_router(r.router, prefix="/api")
    return app


app = create_app()
