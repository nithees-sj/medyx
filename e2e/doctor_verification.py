"""Doctor's view of their own verification. Creates a throwaway pending doctor directly in the
database (no admin notifications), checks the page, and deletes that user again."""

import asyncio
import uuid

from playwright.async_api import async_playwright, expect
from sqlalchemy import delete

from util import BASE, DESKTOP, PHONE, demo_login, shot


async def main() -> None:
    from app.db import SessionLocal
    from app.models import DoctorProfile, User
    from app.security import SESSION_COOKIE, create_session_token

    uid = uuid.uuid4()
    async with SessionLocal() as db:
        db.add(User(id=uid, google_sub=f"e2e:{uid}", email=f"e2e-{uid.hex[:6]}@gmail.com", name="Dr. Kavya Narayanan", role="doctor"))
        await db.flush()
        db.add(
            DoctorProfile(
                user_id=uid, full_name="Dr. Kavya Narayanan", specialty="Cardiology", organization="Lakeview Heart Institute",
                council="Karnataka Medical Council", registration_number="KMC-E2E-4471",
            )  # fmt: skip
        )
        await db.commit()
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch()
            admin = await (await browser.new_context()).new_page()
            await demo_login(admin, "admin")
            r = await admin.request.post(f"{BASE}/api/admin/doctors/{uid}/recheck", headers={"X-HT-Request": "1"})
            assert r.ok, await r.text()
            row = await r.json()
            print("checks:", {c["kind"]: c["status"] for c in row["checks"]}, "risk:", row["risk"])

            for name, viewport in (("doctor_pending_desktop", DESKTOP), ("doctor_pending_phone", PHONE)):
                ctx = await browser.new_context(viewport=viewport)
                await ctx.add_cookies(
                    [{"name": SESSION_COOKIE, "value": create_session_token(str(uid), "doctor", True), "url": BASE}]
                )
                page = await ctx.new_page()
                await page.goto(f"{BASE}/doctor")
                await expect(page.get_by_text("Awaiting verification")).to_be_visible(timeout=20_000)
                await expect(page.get_by_text("What we've checked")).to_be_visible(timeout=15_000)
                await expect(page.get_by_text("Medical register", exact=True)).to_be_visible()
                await expect(page.get_by_role("button", name="Upload registration certificate")).to_be_visible()
                await page.get_by_role("button", name="Correct my details").click()
                await expect(page.get_by_label("Registration number")).to_have_value("KMC-E2E-4471")
                overflow = await page.evaluate("document.documentElement.scrollWidth > window.innerWidth + 1")
                assert not overflow, f"{name} scrolls horizontally"
                await shot(page, name)

            await admin.goto(f"{BASE}/admin/doctors")
            card = admin.locator("article", has_text="Dr. Kavya Narayanan")
            await expect(card).to_be_visible(timeout=15_000)
            await expect(card.get_by_text("Incomplete evidence")).to_be_visible()
            await card.screenshot(path=str(__import__("util").SHOTS / "admin_doctor_card.png"))
            await browser.close()
    finally:
        async with SessionLocal() as db:
            await db.execute(delete(User).where(User.id == uid))
            await db.commit()
        print("cleaned up test doctor", uid)
    print("doctor verification walkthrough: OK")


asyncio.run(main())
