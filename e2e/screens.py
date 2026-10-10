"""Screenshot the main patient screens for a profile (visual check)."""

import asyncio
import sys

from playwright.async_api import async_playwright

from util import BASE, DESKTOP, PHONE, demo_login, shot


async def main(name: str = "Rajan Subramanian", width: str = "desktop") -> None:
    vp = DESKTOP if width == "desktop" else PHONE
    async with async_playwright() as p:
        b = await p.chromium.launch()
        ctx = await b.new_context(viewport=vp)
        page = await ctx.new_page()
        errors: list[str] = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
        await demo_login(page, "priya")
        profiles = await (await page.request.get(f"{BASE}/api/profiles")).json()
        pid = next(x["id"] for x in profiles if x["display_name"] == name)
        for section in sys.argv[3:] or ["timeline", "trends", "medications", "documents"]:
            await page.goto(f"{BASE}/app/p/{pid}/{section}")
            await page.wait_for_load_state("networkidle")
            await page.wait_for_timeout(1500)
            await shot(page, f"p4_{section}_{width}")
        await b.close()
        print("console errors:", [e for e in errors if "favicon" not in e][:10])


asyncio.run(main(sys.argv[1] if len(sys.argv) > 1 else "Rajan Subramanian", sys.argv[2] if len(sys.argv) > 2 else "desktop"))
