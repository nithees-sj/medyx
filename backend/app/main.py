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
from app.routers import admin, auth, doctor, documents, health, notifications, onboarding, profiles, record, review
from app.services.fhir_client import get_fhir
from app.services.ingest.pipeline import worker

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    get_settings().storage_dir.mkdir(parents=True, exist_ok=True)
    await worker.start()
    yield
    await worker.stop()
    await get_fhir().aclose()


def create_app() -> FastAPI:
    settings = get_settings()
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
    for r in (health, auth, onboarding, profiles, documents, review, record, admin, notifications, doctor):
        app.include_router(r.router, prefix="/api")
    return app


app = create_app()
