"""Phase 1 walkthrough: auth redirects, demo personas, onboarding, admin queue."""

import asyncio
import re

from playwright.async_api import async_playwright, expect

from util import BASE, DESKTOP, PHONE, demo_login, mint_session_for_new_user, shot


async def main() -> None:
    async with async_playwright() as p:
        browser = await p.chromium.launch()

        # 1. Protected route without a session → login with ?next=
        ctx = await browser.new_context(viewport=PHONE)
        page = await ctx.new_page()
        await page.goto(f"{BASE}/app")
        await expect(page).to_have_url(re.compile(r"/login\?next=%2Fapp$"))
        await expect(page.get_by_text("Demo accounts")).to_be_visible()
        await shot(page, "p1_login_phone")

        # 2. Demo: unverified doctor sees the verification banner, no patients
        await page.get_by_role("button", name=re.compile("Arjun Mehta")).click()
        await expect(page).to_have_url(f"{BASE}/app")  # ?next=/app wins, then role guard bounces...
        await expect(page).to_have_url(f"{BASE}/doctor", timeout=10_000)
        await expect(page.get_by_text("Awaiting verification")).to_be_visible()
        await expect(page.get_by_text("Your patients")).to_have_count(0)
        await shot(page, "p1_doctor_unverified_phone")
        # Sign out from the account menu
        await page.get_by_label("Account menu").click()
        await page.get_by_role("menuitem", name="Sign out").click()
        await expect(page).to_have_url(re.compile(r"/login"))
        await ctx.close()

        # 3. Admin console lists the pending doctor (desktop)
        ctx = await browser.new_context(viewport=DESKTOP)
        page = await ctx.new_page()
        await demo_login(page, "admin")
        await page.goto(f"{BASE}/admin")
        await expect(page.get_by_text("Dr. Arjun Mehta")).to_be_visible()
        await shot(page, "p1_admin_desktop")
        # Admin is bounced away from the patient app
        await page.goto(f"{BASE}/app")
        await expect(page).to_have_url(f"{BASE}/admin", timeout=10_000)
        await ctx.close()

        # 4. Brand-new user → onboarding → patient profile → /app (phone)
        ctx = await browser.new_context(viewport=PHONE)
        await ctx.add_cookies([{"name": "ht_session", "value": await mint_session_for_new_user(), "url": BASE}])
        page = await ctx.new_page()
        await page.goto(f"{BASE}/app")
        await expect(page).to_have_url(f"{BASE}/onboarding", timeout=10_000)
        await page.get_by_role("button", name=re.compile("patient or family caregiver")).click()
        await page.get_by_role("button", name="Someone I care for").click()
        await page.get_by_label("Their full name").fill("Lakshmi Narayanan")
        await page.get_by_label("They are my…").select_option("parent")
        await page.get_by_label("Date of birth").fill("1958-07-21")
        await page.get_by_label("Sex").select_option("female")
        await page.get_by_label("Blood group").select_option("O+")
        await page.get_by_label("Emergency contact name").fill("Kavya Narayanan")
        await page.get_by_label("Emergency contact phone").fill("+91 98400 11111")
        await shot(page, "p1_onboarding_patient_phone")
        await page.get_by_role("button", name="Create profile").click()
        await expect(page).to_have_url(f"{BASE}/app", timeout=15_000)
        await expect(page.get_by_role("heading", name="Lakshmi Narayanan")).to_be_visible()
        await expect(page.get_by_text(re.compile(r"HT-[A-Z0-9]{4}-[A-Z0-9]{4}"))).to_be_visible()
        await shot(page, "p1_patient_home_phone")
        await ctx.close()

        # 5. Brand-new user → doctor onboarding → pending
        ctx = await browser.new_context(viewport=PHONE)
        await ctx.add_cookies([{"name": "ht_session", "value": await mint_session_for_new_user(), "url": BASE}])
        page = await ctx.new_page()
        await page.goto(f"{BASE}/onboarding")
        await page.get_by_role("button", name=re.compile("I'm a doctor")).click()
        await page.get_by_label("Specialty").select_option("Cardiology")
        await page.get_by_label("Hospital / clinic").fill("Lakeview Heart Institute")
        await page.get_by_label("Medical council").fill("Karnataka Medical Council")
        await page.get_by_label("Registration number").fill("??")
        await page.get_by_role("button", name="Submit for verification").click()
        await expect(page.get_by_text(re.compile("Registration number should look like"))).to_be_visible()
        await page.get_by_label("Registration number").fill("KMC-77812")
        await page.get_by_role("button", name="Submit for verification").click()
        await expect(page).to_have_url(f"{BASE}/doctor", timeout=15_000)
        await expect(page.get_by_text("Awaiting verification")).to_be_visible()
        await ctx.close()

        # 6. QR-style deep link: /share/<token> → login → back to the same URL after sign-in
        ctx = await browser.new_context(viewport=PHONE)
        page = await ctx.new_page()
        await page.goto(f"{BASE}/share/example-token")
        await expect(page).to_have_url(re.compile(r"/login\?next=%2Fshare%2Fexample-token"))
        await expect(page.get_by_text("open the record someone shared")).to_be_visible()
        await page.get_by_role("button", name=re.compile("Meena Raghavan")).click()
        await expect(page).to_have_url(f"{BASE}/share/example-token", timeout=10_000)
        await ctx.close()

        await browser.close()
        print("phase 1 walkthrough: OK")


asyncio.run(main())
