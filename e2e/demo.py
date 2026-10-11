"""The full 3-minute demo (spec §21 / docs/DEMO_SCRIPT.md) on the live stack.

Run after `python -m scripts.seed_demo --reset --stage live`, with the backend and frontend up:
    backend/.venv/bin/python e2e/demo.py
Add `--resume-at=workspace` (or `=prescribe`) to continue after a run that got that far (Rajan ingested
and shared with Dr. Meena) without spending AI quota on the upload, summary and chat again.
"""

import asyncio
import re
import sys
import time

from playwright.async_api import async_playwright, expect

from util import BASE, DESKTOP, PHONE, ROOT, demo_login, shot

RESUME = next((a.split("=", 1)[1] for a in sys.argv[1:] if a.startswith("--resume-at=")), None)
EXPECTED_ALERTS = ["allergy_conflict", "duplicate_therapy", "lab_drift", "prescribing_cascade"]


def step(msg: str, t0: float) -> None:
    print(f"[{time.monotonic() - t0:6.1f}s] {msg}", flush=True)


async def main() -> None:
    t0 = time.monotonic()
    async with async_playwright() as p:
        browser = await p.chromium.launch()

        priya = await (await browser.new_context(viewport=PHONE, is_mobile=True, has_touch=True)).new_page()
        await demo_login(priya, "priya")
        profiles = {x["display_name"]: x["id"] for x in await (await priya.request.get(f"{BASE}/api/profiles")).json()}
        pid = profiles["Rajan Subramanian"]
        doc = await (await browser.new_context(viewport=DESKTOP)).new_page()
        if RESUME:
            await demo_login(doc, "meena")
            # A drug prescribed by an earlier run would (correctly) be flagged as a duplicate.
            meds = (await (await priya.request.get(f"{BASE}/api/profiles/{pid}/medications")).json())["medications"]
            for m in meds:
                if m["generic"] == "azithromycin" and m["status"] == "active":
                    await priya.request.post(
                        f"{BASE}/api/profiles/{pid}/medications/stop", data={"ref": m["ref"]}, headers={"X-HT-Request": "1"}
                    )
            step(f"resuming at {RESUME}", t0)
        else:
            await upload_share_claim(priya, doc, pid, t0)
        await workspace_and_after(browser, priya, doc, pid, t0)
        await browser.close()
        step("full demo walkthrough: OK", t0)


async def upload_share_claim(priya, doc, pid: str, t0: float) -> None:
    # 1. Priya on her phone uploads Rajan's 9 documents from 5 sources
    before = await (await priya.request.get(f"{BASE}/api/profiles/{pid}/documents")).json()
    assert before == [], "run `seed_demo --reset --stage live` first (Rajan should start empty)"
    await priya.goto(f"{BASE}/app/p/{pid}/upload")
    files = sorted((ROOT / "demo_data" / "rajan").iterdir())
    await priya.locator("input[type=file][multiple]").set_input_files([str(f) for f in files])
    await expect(priya.get_by_text(re.compile(r"Processing \d of 9"))).to_be_visible(timeout=30_000)
    await priya.wait_for_timeout(1500)
    await shot(priya, "demo_1_upload_progress")
    await expect(priya.get_by_text("All done")).to_be_visible(timeout=900_000)
    docs = await (await priya.request.get(f"{BASE}/api/profiles/{pid}/documents")).json()
    assert len(docs) == 9 and all(d["status"] in ("done", "needs_review") for d in docs), [
        (d["original_filename"], d["status"], d["error"]) for d in docs
    ]
    step("9 documents processed: " + ", ".join(sorted({d["status"] for d in docs})), t0)
    await shot(priya, "demo_1_upload_done")

    review = await (await priya.request.get(f"{BASE}/api/profiles/{pid}/review")).json()
    if review:
        await priya.goto(f"{BASE}/app/p/{pid}/review")
        for _ in review:
            await priya.get_by_role("button", name="Looks right").first.click()
            await priya.wait_for_timeout(800)
        await expect(priya.get_by_text("Nothing to review")).to_be_visible(timeout=30_000)
    step(f"review queue: {len(review)} item(s) confirmed", t0)

    await priya.goto(f"{BASE}/app/p/{pid}/timeline")
    await expect(priya.locator(".vis-item").first).to_be_visible(timeout=20_000)
    await shot(priya, "demo_1_timeline")

    # 2. Safety: exactly the 4 cross-hospital alerts
    alerts: list[dict] = []
    for _ in range(30):
        alerts = await (await priya.request.get(f"{BASE}/api/profiles/{pid}/alerts")).json()
        if sorted(a["type"] for a in alerts) == EXPECTED_ALERTS:
            break
        await priya.wait_for_timeout(2000)
    assert sorted(a["type"] for a in alerts) == EXPECTED_ALERTS, [a["type"] for a in alerts]
    assert [a["severity"] for a in alerts if a["type"] == "allergy_conflict"] == ["critical"]
    await priya.goto(f"{BASE}/app/p/{pid}/alerts")
    await expect(priya.locator("article")).to_have_count(4, timeout=20_000)
    await expect(priya.get_by_text(re.compile("Penicillin", re.IGNORECASE)).first).to_be_visible()
    await shot(priya, "demo_2_alerts")
    await priya.goto(f"{BASE}/app/p/{pid}/trends")
    await expect(priya.get_by_text("eGFR").first).to_be_visible(timeout=20_000)
    await shot(priya, "demo_2_trends")
    step("4 alerts: " + ", ".join(sorted(a["type"] for a in alerts)), t0)

    # 3. Share: 7-day QR, default scopes, doctor may add & prescribe
    await priya.goto(f"{BASE}/app/p/{pid}/sharing")
    await priya.get_by_label("Allow doctor to add documents and prescriptions").click()
    async with priya.expect_response(lambda r: r.url.endswith("/shares") and r.request.method == "POST") as created:
        await priya.get_by_role("button", name="Create QR code").click()
    share = await (await created.value).json()
    assert sorted(share["consent"]["scopes"]) == ["allergies", "conditions", "labs", "medications"]
    assert share["consent"]["duration_hours"] == 168 and share["consent"]["can_write"] is True
    await expect(priya.get_by_label("Share QR code")).to_be_visible()
    await shot(priya, "demo_3_share_qr")
    step("QR share created", t0)

    # 4. Dr. Meena on a laptop: QR link → sign in → claim → dashboard → summary → copilot → citation
    await doc.goto(share["url"])
    await expect(doc).to_have_url(re.compile(r"/login\?next=%2Fshare%2F"))
    await doc.get_by_role("button", name=re.compile("Meena Raghavan")).click()
    await expect(doc).to_have_url(re.compile(r"/share/"), timeout=15_000)
    await doc.get_by_role("button", name=re.compile("Open Rajan")).click()
    await expect(doc).to_have_url(re.compile(rf"/doctor/patients/{pid}"), timeout=15_000)
    await doc.goto(f"{BASE}/doctor")
    rows = doc.locator("tbody tr")
    await expect(rows.first).to_contain_text("Rajan Subramanian", timeout=15_000)
    await expect(rows.first).to_contain_text("1 critical")
    await expect(rows.first).to_contain_text("3 warnings")
    await shot(doc, "demo_4_dashboard")
    step("doctor dashboard: Rajan first, 1 critical · 3 warnings", t0)

    await doc.get_by_role("button", name="Which of my patients have declining kidney function?").click()
    table = doc.locator("section", has_text="Panel insights").locator("table")
    await expect(table).to_be_visible(timeout=180_000)
    await expect(table).to_contain_text("Rajan Subramanian")
    await expect(table).not_to_contain_text("Lakshmi")
    await shot(doc, "demo_4_insights")
    step("panel insights: Rajan, not Lakshmi", t0)



async def workspace_and_after(browser, priya, doc, pid: str, t0: float) -> None:
    await doc.goto(f"{BASE}/doctor/patients/{pid}")
    await expect(doc.get_by_role("heading", name="Rajan Subramanian")).to_be_visible(timeout=15_000)
    if RESUME != "prescribe":
        await summary_and_copilot(doc, t0)
    await prescribe_control_emergency(browser, priya, doc, pid, t0)


async def summary_and_copilot(doc, t0: float) -> None:
    await expect(doc.get_by_label("Specialty")).to_have_value("Nephrology")
    await expect(doc.get_by_text("Key problems")).to_be_visible(timeout=180_000)
    await shot(doc, "demo_4_summary")
    step("nephrology summary ready", t0)

    await doc.get_by_label("Ask a question about this record").fill(
        "When did kidney function start declining and what was he taking then?"
    )
    await doc.get_by_role("button", name="Send").click()
    chips = doc.locator("aside button", has_text=re.compile(r"D\d+ p\d+"))
    await expect(chips.first).to_be_visible(timeout=180_000)
    # Quick prompts are disabled while an answer streams.
    await expect(doc.get_by_role("button", name="Draft a referral letter to cardiology")).to_be_enabled(timeout=180_000)
    n_chips = await chips.count()
    assert n_chips >= 3, f"expected several citations, got {n_chips}"
    await shot(doc, "demo_4_chat")
    egfr = chips.filter(has_text=re.compile("eGFR"))
    await (egfr.first if await egfr.count() else chips.first).click()
    dialog = doc.get_by_role("dialog")
    await expect(dialog.get_by_text(re.compile("Quoted from page"))).to_be_visible(timeout=15_000)
    await expect(dialog.locator("mark.ht-mark").first).to_be_visible(timeout=20_000)
    await shot(doc, "demo_4_citation")
    await doc.keyboard.press("Escape")
    step(f"copilot answer with {n_chips} citations; source page opened and highlighted", t0)



async def prescribe_control_emergency(browser, priya, doc, pid: str, t0: float) -> None:
    # 5. Prevention: Novamox 500 is blocked by the allergy; Azithral is prescribed
    await doc.get_by_role("button", name="Prescribe").first.click()
    await doc.get_by_label("Medicine (brand or generic)").fill("Novamox 500")
    await expect(doc.get_by_text(re.compile(r"Critical: Penicillin allergy vs amoxicillin"))).to_be_visible(timeout=15_000)
    await expect(doc.get_by_role("button", name=re.compile("Prescribe anyway"))).to_be_disabled()
    await shot(doc, "demo_5_prescribe_blocked")
    await doc.get_by_label("Medicine (brand or generic)").fill("Azithral")
    await doc.get_by_role("button", name=re.compile(r"^Azithral")).click()
    await doc.get_by_label("Duration (days)").fill("3")
    await doc.get_by_role("button", name="1-0-0").click()
    await expect(doc.get_by_text(re.compile("No conflicts found"))).to_be_visible(timeout=15_000)
    await doc.get_by_role("button", name="Prescribe", exact=True).click()
    await expect(doc.get_by_text(re.compile("prescribed$"))).to_be_visible(timeout=15_000)
    print_link = doc.get_by_role("link", name="Print prescription")
    await expect(print_link).to_be_visible()
    pdf = await doc.request.get(f"{BASE}{await print_link.get_attribute('href')}")
    assert pdf.ok and (await pdf.body()).startswith(b"%PDF"), pdf.status
    await shot(doc, "demo_5_prescribed")
    step("Novamox blocked; Azithral prescribed", t0)

    # 6. Control: access log, then revoke → the doctor loses access
    await priya.goto(f"{BASE}/app/p/{pid}/access-log")
    await expect(priya.get_by_text(re.compile("Dr. Meena Raghavan")).first).to_be_visible(timeout=15_000)
    await expect(priya.get_by_text(re.compile("viewed lab results")).first).to_be_visible()
    await shot(priya, "demo_6_access_log")
    await priya.goto(f"{BASE}/app/p/{pid}/sharing")
    await priya.get_by_role("button", name="Revoke").first.click()
    await priya.get_by_role("button", name="Revoke access").click()
    await expect(priya.get_by_text("Only you can see this record")).to_be_visible(timeout=10_000)
    await doc.reload()
    await expect(doc.get_by_text("You no longer have access to this record")).to_be_visible(timeout=15_000)
    await shot(doc, "demo_6_revoked")
    step("revoked; doctor sees access denied", t0)

    # 7. Emergency card: responder sees only the emergency fields; Priya is notified
    await priya.goto(f"{BASE}/app/p/{pid}/emergency")
    async with priya.expect_response(lambda r: r.url.endswith("/emergency/enable")) as en:
        await priya.get_by_role("button", name=re.compile("Turn on emergency card|Create a new card")).first.click()
    card = await (await en.value).json()
    responder = await (await browser.new_context(viewport=PHONE)).new_page()
    await responder.goto(card["url"])
    await expect(responder.get_by_text("Penicillin").first).to_be_visible(timeout=10_000)
    await expect(responder.get_by_text("B+")).to_be_visible()
    await expect(responder.get_by_text(re.compile("eGFR|Creatinine"))).to_have_count(0)
    await shot(responder, "demo_7_emergency_card")
    await priya.reload()
    await priya.get_by_role("button", name=re.compile(r"^Notifications")).click()
    await expect(priya.get_by_text(re.compile("Emergency access to Rajan's card")).first).to_be_visible(timeout=20_000)
    await shot(priya, "demo_7_notification")
    step("emergency card viewed; owner notified", t0)

    overflow = await priya.evaluate("document.documentElement.scrollWidth > window.innerWidth + 1")
    assert not overflow, "page scrolls horizontally on a phone"


asyncio.run(main())
