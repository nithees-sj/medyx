"""Shared helpers for the Playwright walkthroughs (run with backend/.venv/bin/python)."""

import os
import sys
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
os.chdir(ROOT / "backend")

BASE = os.environ.get("E2E_BASE", "http://localhost:3000")
SHOTS = Path(os.environ.get("E2E_SHOTS", ROOT / "e2e" / "screenshots"))
SHOTS.mkdir(parents=True, exist_ok=True)
PHONE = {"width": 390, "height": 844}
DESKTOP = {"width": 1440, "height": 900}


async def mint_session_for_new_user(email: str | None = None) -> str:
    """Create a brand-new (not onboarded) user directly and return a session token.

    Stands in for Google sign-in, which can't be automated headlessly.
    """
    from app.db import SessionLocal
    from app.models import User
    from app.security import create_session_token

    async with SessionLocal() as db:
        u = User(
            google_sub=f"e2e:{uuid.uuid4()}",
            email=email or f"e2e-{uuid.uuid4().hex[:6]}@example.com",
            name="Kavya Narayanan",
        )
        db.add(u)
        await db.commit()
        return create_session_token(str(u.id), None, False)


async def demo_login(page, persona: str) -> None:
    resp = await page.request.post(f"{BASE}/api/auth/demo", data={"persona": persona}, headers={"X-HT-Request": "1"})
    assert resp.ok, await resp.text()


async def shot(page, name: str) -> None:
    await page.wait_for_timeout(400)
    await page.screenshot(path=str(SHOTS / f"{name}.png"), full_page=True)
