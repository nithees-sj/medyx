"""Application settings, loaded from the repo-root `.env` file and the environment."""

from functools import lru_cache
from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = BACKEND_DIR.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(REPO_ROOT / ".env", BACKEND_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Auth
    google_client_id: str = ""
    jwt_secret: str = "change-me"
    jwt_expiry_hours: int = 8
    admin_emails: str = ""

    # AI
    gemini_api_key: str = ""
    gemini_model: str = "gemini-3.5-flash"
    ai_timeout_seconds: float = 120.0
    # Requests/minute allowed by the key's quota. Free Gemini tier = 5; raise it on a paid key.
    ai_requests_per_minute: int = 5

    # Data
    database_url: str = "postgresql+psycopg://healththread:healththread@localhost:5432/healththread"
    test_database_url: str = "postgresql+psycopg://healththread:healththread@localhost:5432/healththread_test"
    fhir_base_url: str = "http://localhost:8080/fhir"
    storage_dir: Path = REPO_ROOT / "storage"
    demo_cache_dir: Path = BACKEND_DIR / "demo_cache"
    demo_data_dir: Path = REPO_ROOT / "demo_data"

    # App
    app_base_url: str = "http://localhost:3000"
    demo_mode: bool = False
    demo_cache: bool = False
    default_timezone: str = "Asia/Kolkata"

    @field_validator("storage_dir", mode="after")
    @classmethod
    def _resolve_storage(cls, v: Path) -> Path:
        # Relative paths in .env are relative to the repo root, not the cwd.
        return v if v.is_absolute() else (REPO_ROOT / v).resolve()

    @property
    def admin_email_set(self) -> set[str]:
        return {e.strip().lower() for e in self.admin_emails.split(",") if e.strip()}

    @property
    def cookie_secure(self) -> bool:
        return not self.app_base_url.startswith("http://localhost")


@lru_cache
def get_settings() -> Settings:
    return Settings()
