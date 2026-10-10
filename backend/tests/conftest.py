import os

# Point the app at the isolated test database *before* anything imports app.db.
from app.config import get_settings

os.environ["DATABASE_URL"] = get_settings().test_database_url
get_settings.cache_clear()

import httpx  # noqa: E402
import pytest  # noqa: E402
from sqlalchemy import text  # noqa: E402

import app.models  # noqa: E402,F401
from app.db import Base, SessionLocal, engine  # noqa: E402
from app.main import app as fastapi_app  # noqa: E402
from app.models import DoctorProfile, User  # noqa: E402
from app.rate_limit import limiter  # noqa: E402
from app.security import SESSION_COOKIE, create_session_token  # noqa: E402
from app.services.fhir_client import FhirClient, set_fhir  # noqa: E402
from tests.fakes import FakeFhirClient  # noqa: E402

assert "healththread_test" in str(engine.url), "tests must never run against the app database"
limiter.enabled = False


@pytest.fixture(scope="session", autouse=True)
async def _schema():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield
    await engine.dispose()


@pytest.fixture(autouse=True)
async def _clean_tables():
    yield
    names = ", ".join(t.name for t in reversed(Base.metadata.sorted_tables))
    async with engine.begin() as conn:
        await conn.execute(text(f"TRUNCATE {names} CASCADE"))


@pytest.fixture(autouse=True)
def fhir(request):
    """Fake FHIR by default; tests marked `integration` get the real HAPI server."""
    if request.node.get_closest_marker("integration"):
        client = FhirClient(get_settings().fhir_base_url)
        set_fhir(client)
        yield client
    else:
        fake = FakeFhirClient()
        set_fhir(fake)
        yield fake
    set_fhir(None)


@pytest.fixture(autouse=True)
def _no_background_ai(monkeypatch):
    """Alert explanations are upgraded by a background AI call in the app; tests keep the templates."""
    monkeypatch.setattr("app.services.safety.engine.schedule_explanations", lambda *a, **k: None)


@pytest.fixture
def settings():
    s = get_settings()
    original = s.model_dump()
    yield s
    for k, v in original.items():
        setattr(s, k, v)


@pytest.fixture
async def db():
    async with SessionLocal() as session:
        yield session


@pytest.fixture
async def client():
    transport = httpx.ASGITransport(app=fastapi_app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test", headers={"X-HT-Request": "1"}) as c:
        yield c


async def make_user(
    db, *, email: str, role: str | None = None, name: str = "Test User", doctor_status: str | None = None
) -> User:
    user = User(google_sub=f"sub-{email}", email=email, name=name, role=role)
    db.add(user)
    await db.flush()
    if doctor_status:
        db.add(
            DoctorProfile(
                user_id=user.id,
                full_name=name,
                specialty="Nephrology",
                organization="Test Hospital",
                council="Test Council",
                registration_number="TC-12345",
                verification_status=doctor_status,
            )
        )
    await db.commit()
    await db.refresh(user)
    return user


def login(client: httpx.AsyncClient, user: User) -> httpx.AsyncClient:
    client.cookies.set(SESSION_COOKIE, create_session_token(str(user.id), user.role, user.onboarded))
    return client
