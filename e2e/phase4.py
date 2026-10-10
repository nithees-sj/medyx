"""Phase 4 acceptance: Priya completes upload → review → timeline on a phone-width screen."""

import asyncio
import re
import uuid

from playwright.async_api import async_playwright, expect

from util import BASE, PHONE, ROOT, demo_login, shot

DOCS = [
    ROOT / "demo_data/rajan/sunrise_2024-03-12_opd.pdf",
    ROOT / "demo_data/rajan/sunrise_2024-03-12_lab.pdf",
    ROOT / "demo_data/rajan/anand_2026-02-18_rx.png",
]


async def main() -> None:
    name = f"Kumar Test {uuid.uuid4().hex[:4].upper()}"
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        ctx = await browser.new_context(viewport=PHONE, device_scale_factor=2, is_mobile=True, has_touch=True)
        page = await ctx.new_page()
        await demo_login(page, "priya")
        await page.goto(f"{BASE}/app")

        # Add a family member from the home screen
        await page.get_by_role("button", name="Add family member").first.click()
        await page.get_by_label("Their full name").fill(name)
        await page.get_by_label("They are my…").select_option("parent")
        await page.get_by_label("Date of birth").fill("1961-11-02")
        await page.get_by_label("Sex").select_option("male")
        await page.get_by_role("button", name="Create profile").click()
        await expect(page.get_by_role("heading", name=name)).to_be_visible(timeout=15_000)

        # Upload three documents from different sources
        await page.get_by_role("link", name="Upload", exact=True).first.click()
        await expect(page).to_have_url(re.compile(r"/app/p/.+/upload$"))
        await page.locator("input[type=file][multiple]").set_input_files([str(d) for d in DOCS])
        await expect(page.get_by_text(re.compile(r"Processing \d of 3|All done"))).to_be_visible(timeout=20_000)
        await page.wait_for_timeout(1500)
        await shot(page, "p4_upload_progress_phone")
        await expect(page.get_by_text("All done")).to_be_visible(timeout=300_000)
        await expect(page.get_by_text(re.compile(r"lab values?"))).to_have_count(2)
        await shot(page, "p4_upload_done_phone")

        # Review the item we weren't sure about
        await page.get_by_role("link", name="Review items").click()
        await expect(page.get_by_text("Penicillin — skin rash").first).to_be_visible(timeout=15_000)
        await shot(page, "p4_review_phone")
        await page.get_by_role("button", name="Looks right").click()
        await expect(page.get_by_text("Nothing to review")).to_be_visible(timeout=20_000)

        # The unified timeline
        await page.get_by_role("link", name="Timeline", exact=True).click()
        await expect(page.locator(".vis-item").first).to_be_visible(timeout=15_000)
        await expect(page.get_by_text("Type 2 diabetes mellitus").first).to_be_visible()
        await expect(page.get_by_text("Sunrise Diabetes & Multispeciality Hospital").first).to_be_visible()
        await expect(page.get_by_text("Anand Family Clinic").first).to_be_visible()
        await shot(page, "p4_timeline_after_upload_phone")

        # Tap a timeline item → source drawer → open the original page
        await page.locator(".vis-item", has_text="Type 2 diabetes mellitus").first.click()
        await expect(page.get_by_role("dialog")).to_be_visible()
        await page.get_by_role("button", name=re.compile(r"D\d+ · page 1")).first.click()
        await expect(page.get_by_text("Quoted from page 1")).to_be_visible(timeout=15_000)
        await page.wait_for_timeout(2500)
        await shot(page, "p4_viewer_phone")

        # No horizontal scroll on the phone
        overflow = await page.evaluate("document.documentElement.scrollWidth > window.innerWidth + 1")
        assert not overflow, "page scrolls horizontally on a phone"
        await browser.close()
        print("phase 4 walkthrough: OK")


asyncio.run(main())
