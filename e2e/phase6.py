"""Phase 6 walkthrough: QR share → doctor signs in → claim; access log; emergency card; revoke."""

import asyncio
import re

from playwright.async_api import async_playwright, expect

from util import BASE, DESKTOP, PHONE, demo_login, shot


async def main() -> None:
    async with async_playwright() as p:
        browser = await p.chromium.launch()

        # Priya (phone) creates a QR share for Rajan
        priya_ctx = await browser.new_context(viewport=PHONE)
        priya = await priya_ctx.new_page()
        await demo_login(priya, "priya")
        profiles = await (await priya.request.get(f"{BASE}/api/profiles")).json()
        pid = next(x["id"] for x in profiles if x["display_name"] == "Rajan Subramanian")
        # Clean slate: revoke any earlier active shares for a predictable walkthrough
        for c in await (await priya.request.get(f"{BASE}/api/profiles/{pid}/consents")).json():
            if c["status"] in ("active", "pending_claim", "requested"):
                await priya.request.post(f"{BASE}/api/consents/{c['id']}/revoke", headers={"X-HT-Request": "1"})
        await priya.goto(f"{BASE}/app/p/{pid}/sharing")
        async with priya.expect_response(lambda r: r.url.endswith("/shares") and r.request.method == "POST") as created:
            await priya.get_by_role("button", name="Create QR code").click()
        share = await (await created.value).json()
        await expect(priya.get_by_label("Share QR code")).to_be_visible()
        await expect(priya.get_by_text("Waiting for the doctor to scan")).to_be_visible()
        await shot(priya, "p6_share_qr_phone")

        # Dr. Meena (laptop, signed out) opens the QR link → login → back to the claim page
        doc_ctx = await browser.new_context(viewport=DESKTOP)
        doc = await doc_ctx.new_page()
        await doc.goto(share["url"])
        await expect(doc).to_have_url(re.compile(r"/login\?next=%2Fshare%2F"))
        await doc.get_by_role("button", name=re.compile("Meena Raghavan")).click()
        await expect(doc).to_have_url(re.compile(r"/share/"), timeout=15_000)
        await expect(doc.get_by_text("Rajan Subramanian")).to_be_visible()
        await shot(doc, "p6_claim_desktop")
        await doc.get_by_role("button", name=re.compile("Open Rajan")).click()
        await expect(doc).to_have_url(re.compile(rf"/doctor/patients/{pid}"), timeout=15_000)

        # Priya sees the doctor connected, and it's in the access log
        await expect(priya.get_by_text("Dr. Meena Raghavan is connected")).to_be_visible(timeout=15_000)
        await shot(priya, "p6_connected_phone")
        await doc.request.get(f"{BASE}/api/profiles/{pid}/trends")  # a doctor view to log
        await priya.goto(f"{BASE}/app/p/{pid}/access-log")
        await expect(priya.get_by_text(re.compile("opened the shared record")).first).to_be_visible(timeout=10_000)
        await expect(priya.get_by_text(re.compile("viewed lab results & vitals")).first).to_be_visible()
        await shot(priya, "p6_access_log_phone")

        # Emergency card: Priya turns it on; an anonymous responder scans it
        await priya.goto(f"{BASE}/app/p/{pid}/emergency")
        enable = priya.get_by_role("button", name=re.compile("Turn on emergency card|Create a new card"))
        async with priya.expect_response(lambda r: r.url.endswith("/emergency/enable")) as en:
            await enable.first.click()
        card = await (await en.value).json()
        await expect(priya.get_by_label("Emergency card QR code")).to_be_visible()
        await shot(priya, "p6_emergency_phone")
        responder = await (await browser.new_context(viewport=PHONE)).new_page()
        await responder.goto(card["url"])
        await expect(responder.get_by_text("Penicillin")).to_be_visible(timeout=10_000)
        await expect(responder.get_by_text("B+")).to_be_visible()
        await expect(responder.get_by_text(re.compile("eGFR|Creatinine"))).to_have_count(0)
        await shot(responder, "p6_public_card_phone")
        await priya.reload()
        await priya.get_by_role("button", name=re.compile(r"^Notifications")).click()
        await expect(priya.get_by_text(re.compile("Emergency access to Rajan's card")).first).to_be_visible(timeout=20_000)
        await priya.keyboard.press("Escape")

        # Revoke → the doctor's next request is refused
        await priya.goto(f"{BASE}/app/p/{pid}/sharing")
        await priya.get_by_role("button", name="Revoke").first.click()
        await priya.get_by_role("button", name="Revoke access").click()
        await expect(priya.get_by_text("Only you can see this record")).to_be_visible(timeout=10_000)
        r = await doc.request.get(f"{BASE}/api/profiles/{pid}/timeline")
        assert r.status == 403, r.status

        await browser.close()
        print("phase 6 walkthrough: OK")


asyncio.run(main())
