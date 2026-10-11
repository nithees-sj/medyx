"""Admin console walkthrough (read-only): overview, doctor verification, activity log, system, users."""

import asyncio
import re

from playwright.async_api import async_playwright, expect

from util import BASE, DESKTOP, PHONE, demo_login, shot


async def main() -> None:
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        admin = await (await browser.new_context(viewport=DESKTOP)).new_page()
        errors: list[str] = []
        admin.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
        await demo_login(admin, "admin")
        pending = await (await admin.request.get(f"{BASE}/api/admin/doctors?status_filter=pending")).json()
        print("pending doctors:", [(d["full_name"], d["risk"]) for d in pending])

        await admin.goto(f"{BASE}/admin")
        await expect(admin.get_by_role("heading", name="Platform overview")).to_be_visible(timeout=20_000)
        await expect(admin.get_by_text("Activity, last 14 days")).to_be_visible()
        await expect(admin.get_by_text("Needs attention")).to_be_visible()
        await admin.wait_for_timeout(1500)
        await shot(admin, "admin_overview")

        await admin.get_by_role("link", name="Doctors", exact=True).click()
        await expect(admin.get_by_role("heading", name="Doctor verification")).to_be_visible()
        await expect(admin.get_by_text("Medical register not connected").first).to_be_visible(timeout=15_000)
        await expect(admin.get_by_text("Trusted hospital email domains", exact=True)).to_be_visible()
        if not pending:
            await expect(admin.get_by_text("No applications waiting")).to_be_visible()
        await shot(admin, "admin_doctors")
        await admin.get_by_role("tab", name="Verified").click()
        await expect(admin.locator("article", has_text="Dr. Meena Raghavan")).to_be_visible(timeout=15_000)
        await shot(admin, "admin_doctors_verified")

        await admin.get_by_role("link", name="Activity", exact=True).click()
        await expect(admin.get_by_role("heading", name="Activity log")).to_be_visible()
        await expect(admin.get_by_text(re.compile("signed in")).first).to_be_visible(timeout=15_000)
        await shot(admin, "admin_activity")

        await admin.get_by_role("link", name="System", exact=True).click()
        await expect(admin.get_by_role("heading", name="System", exact=True)).to_be_visible()
        await expect(admin.get_by_text("API traffic")).to_be_visible(timeout=15_000)
        await expect(admin.get_by_text("AI usage")).to_be_visible(timeout=15_000)
        await admin.wait_for_timeout(1500)
        await shot(admin, "admin_system")

        await admin.get_by_role("link", name="Users", exact=True).click()
        await expect(admin.get_by_role("heading", name="Users")).to_be_visible()
        await admin.get_by_label("Search by name or email").fill("arjun")
        await expect(admin.get_by_text("arjun.mehta@demo.healththread.app")).to_be_visible(timeout=10_000)
        await shot(admin, "admin_users")

        phone = await (await browser.new_context(viewport=PHONE, is_mobile=True, has_touch=True)).new_page()
        await demo_login(phone, "admin")
        await phone.goto(f"{BASE}/admin")
        await expect(phone.get_by_role("heading", name="Platform overview")).to_be_visible(timeout=20_000)
        await phone.wait_for_timeout(1200)
        overflow = await phone.evaluate("document.documentElement.scrollWidth > window.innerWidth + 1")
        await shot(phone, "admin_overview_phone")
        assert not overflow, "admin overview scrolls horizontally on a phone"

        bad = [e for e in errors if "favicon" not in e]
        assert not bad, bad
        await browser.close()
        print("admin walkthrough: OK")


asyncio.run(main())
