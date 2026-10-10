"""Phase 7 acceptance on the live stack (real Gemini):
- Dr. Meena asks the kidney question and gets a cited answer whose chips open the right pages
- Typing "Novamox 500" in the prescribe drawer shows the penicillin allergy alert before saving
- "Which of my patients have declining kidney function?" returns Rajan with a sparkline, not Lakshmi
"""

import asyncio
import re

from playwright.async_api import async_playwright, expect

from util import BASE, DESKTOP, demo_login, shot

H = {"X-HT-Request": "1"}


async def share(page, pid: str, scopes: list[str]) -> str:
    r = await page.request.post(f"{BASE}/api/profiles/{pid}/shares", data={"scopes": scopes, "duration_hours": 168, "can_write": True}, headers=H)
    return (await r.json())["token"]


async def main() -> None:
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        priya = await (await browser.new_context(viewport=DESKTOP)).new_page()
        await demo_login(priya, "priya")
        profiles = {x["display_name"]: x["id"] for x in await (await priya.request.get(f"{BASE}/api/profiles")).json()}
        rajan, lakshmi = profiles["Rajan Subramanian"], profiles["Lakshmi Iyer"]
        scopes = ["conditions", "medications", "allergies", "labs"]

        ctx = await browser.new_context(viewport=DESKTOP)
        doc = await ctx.new_page()
        await demo_login(doc, "meena")
        for pid in (rajan, lakshmi):
            token = await share(priya, pid, scopes)
            r = await doc.request.post(f"{BASE}/api/share/{token}/claim", headers=H)
            assert r.ok, await r.text()

        # Dashboard: Rajan first (critical alert), Lakshmi below
        await doc.goto(f"{BASE}/doctor")
        rows = doc.locator("tbody tr")
        await expect(rows.first).to_contain_text("Rajan Subramanian", timeout=15_000)
        await expect(rows.first).to_contain_text("1 critical")
        await shot(doc, "p7_dashboard")

        # Panel insights with tools
        await doc.get_by_role("button", name="Which of my patients have declining kidney function?").click()
        table = doc.locator("section", has_text="Panel insights").locator("table")
        await expect(table).to_be_visible(timeout=120_000)
        await expect(table).to_contain_text("Rajan Subramanian")
        await expect(table).not_to_contain_text("Lakshmi")
        await expect(table.get_by_role("img", name=re.compile("eGFR")).first).to_be_visible()
        assert await table.locator("tbody tr").count() == 1
        await shot(doc, "p7_insights")

        # Workspace → copilot question with citations
        await doc.goto(f"{BASE}/doctor/patients/{rajan}")
        await expect(doc.get_by_role("heading", name="Rajan Subramanian")).to_be_visible(timeout=15_000)
        box = doc.get_by_label("Ask a question about this record")
        await box.fill("When did kidney function start declining and what was he taking then?")
        await doc.get_by_role("button", name="Send").click()
        chips = doc.locator("aside button", has_text=re.compile(r"D\d+ p\d+"))
        await expect(chips.first).to_be_visible(timeout=120_000)
        answer = await doc.locator("aside").inner_text()
        print("--- copilot answer ---\n", answer[answer.find("When did kidney"):][:1500])
        n_chips = await chips.count()
        assert n_chips >= 3, f"expected several citations, got {n_chips}"
        await shot(doc, "p7_chat")
        # Click a citation for an eGFR value → the lab report page opens with the quote highlighted
        egfr_chip = chips.filter(has_text=re.compile("eGFR")).first
        await egfr_chip.click()
        dialog = doc.get_by_role("dialog")
        await expect(dialog.get_by_text(re.compile("Quoted from page"))).to_be_visible(timeout=15_000)
        await expect(dialog.locator("mark.ht-mark").first).to_be_visible(timeout=20_000)
        await shot(doc, "p7_citation_viewer")
        await doc.keyboard.press("Escape")

        # Summary tab (nephrology)
        await expect(doc.get_by_text("Key problems")).to_be_visible(timeout=120_000)
        await shot(doc, "p7_summary")

        # Prescribe drawer: Novamox 500 → live allergy alert before saving
        await doc.get_by_role("button", name="Prescribe").first.click()
        await doc.get_by_label("Medicine (brand or generic)").fill("Novamox 500")
        alert = doc.get_by_text(re.compile(r"Critical: Penicillin allergy vs amoxicillin"))
        await expect(alert).to_be_visible(timeout=15_000)
        await expect(doc.get_by_role("button", name=re.compile("Prescribe anyway"))).to_be_disabled()
        await shot(doc, "p7_prescribe_alert")
        # Pick a safe alternative and save
        await doc.get_by_label("Medicine (brand or generic)").fill("Azithral")
        await doc.get_by_role("button", name=re.compile(r"^Azithral")).click()
        await doc.get_by_label("Duration (days)").fill("3")
        await doc.get_by_role("button", name="1-0-0").click()
        await expect(doc.get_by_text(re.compile("No conflicts found"))).to_be_visible(timeout=15_000)
        await doc.get_by_role("button", name="Prescribe", exact=True).click()
        await expect(doc.get_by_text(re.compile("prescribed$"))).to_be_visible(timeout=15_000)
        await shot(doc, "p7_prescribed")

        await browser.close()
        print("phase 7 walkthrough: OK")


asyncio.run(main())
