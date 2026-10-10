"""Emergency card renderings: the public summary, a wallet-card PDF and a lock-screen PNG."""

import io
from datetime import date
from typing import Any

import qrcode
from PIL import Image, ImageDraw, ImageFont
from reportlab.lib.colors import HexColor, white
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen.canvas import Canvas

from app.services.profiles import age_on
from app.services.record import PatientRecord

FONT_DIR = __import__("pathlib").Path(__file__).resolve().parents[2] / "scripts" / "assets" / "fonts"


def card_data(record: PatientRecord, profile: Any, today: date) -> dict[str, Any]:
    """Only what a responder needs. No labs, no documents."""
    return {
        "name": profile.display_name,
        "age": age_on(profile.dob, today),
        "sex": profile.sex,
        "blood_group": profile.blood_group,
        "allergies": [
            {"substance": a.substance, "reaction": a.reaction, "criticality": a.criticality} for a in record.allergies
        ],
        "medications": [
            {"name": m.display, "brand": m.brand, "frequency": m.frequency_label}
            for m in record.medications
            if m.active_on(today)
        ],
        "conditions": [c.text for c in record.conditions if c.clinical_status == "active" and not c.mental_health],
        "emergency_contact": {"name": profile.emergency_contact_name, "phone": profile.emergency_contact_phone}
        if profile.emergency_contact_name or profile.emergency_contact_phone
        else None,
        "healththread_id": profile.healththread_id,
    }


def _qr(url: str, box: int = 10) -> Image.Image:
    q = qrcode.QRCode(error_correction=qrcode.constants.ERROR_CORRECT_M, box_size=box, border=2)
    q.add_data(url)
    q.make(fit=True)
    return q.make_image(fill_color="black", back_color="white").convert("RGB")


def wallet_pdf(data: dict[str, Any], url: str) -> bytes:
    """Credit-card size (85.6 × 54 mm) card: front with QR and the essentials."""
    w, h = 85.6 * mm, 53.98 * mm
    buf = io.BytesIO()
    c = Canvas(buf, pagesize=(w, h))
    c.setTitle(f"Emergency card — {data['name']}")
    teal, red = HexColor("#0f6e6e"), HexColor("#b42318")
    c.setFillColor(teal)
    c.rect(0, h - 9 * mm, w, 9 * mm, fill=1, stroke=0)
    c.setFillColor(white)
    c.setFont("Helvetica-Bold", 8)
    c.drawString(3 * mm, h - 6 * mm, "EMERGENCY MEDICAL INFORMATION")
    c.setFont("Helvetica", 6)
    c.drawRightString(w - 3 * mm, h - 6 * mm, "HealthThread")
    c.drawImage(ImageReader(_qr(url, 6)), w - 27 * mm, 3 * mm, 24 * mm, 24 * mm)
    c.setFillColor(HexColor("#111111"))
    c.setFont("Helvetica-Bold", 10)
    c.drawString(3 * mm, h - 15 * mm, data["name"][:28])
    c.setFont("Helvetica", 7)
    c.drawString(3 * mm, h - 19 * mm, f"{data['age']} yrs · {data['sex']} · Blood group {data['blood_group']}")
    c.setFillColor(red)
    c.setFont("Helvetica-Bold", 7)
    allergies = ", ".join(a["substance"] for a in data["allergies"]) or "None recorded"
    c.drawString(3 * mm, h - 24 * mm, f"ALLERGIES: {allergies}"[:46])
    c.setFillColor(HexColor("#333333"))
    c.setFont("Helvetica", 6)
    meds = ", ".join(m["name"].split(" ")[0] for m in data["medications"])[:120]
    y = h - 28.5 * mm
    for line in [f"Medicines: {meds}" if meds else "Medicines: none recorded"]:
        c.drawString(3 * mm, y, line[:58])
        y -= 3 * mm
    ec = data.get("emergency_contact")
    if ec:
        c.setFont("Helvetica-Bold", 6.5)
        c.drawString(3 * mm, 8 * mm, f"ICE: {ec.get('name') or ''} {ec.get('phone') or ''}"[:48])
    c.setFont("Helvetica", 5.5)
    c.setFillColor(HexColor("#666666"))
    c.drawString(3 * mm, 3.5 * mm, "Scan the QR for the full emergency card")
    c.showPage()
    c.save()
    return buf.getvalue()


def lockscreen_png(data: dict[str, Any], url: str) -> bytes:
    """1170 × 2532 phone wallpaper with the QR, name and blood group."""
    W, H = 1170, 2532
    img = Image.new("RGB", (W, H), (15, 110, 110))
    d = ImageDraw.Draw(img)

    def font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
        f = ImageFont.truetype(str(FONT_DIR / "Lora.ttf"), size)
        f.set_variation_by_name("Bold" if bold else "Regular")
        return f

    d.text((W // 2, 1030), "EMERGENCY MEDICAL INFO", font=font(54, True), fill="white", anchor="mm")
    d.text((W // 2, 1110), "Scan for allergies, medicines & contact", font=font(40), fill=(220, 240, 240), anchor="mm")
    qr = _qr(url, 18).resize((620, 620), Image.Resampling.NEAREST)
    panel = Image.new("RGB", (700, 700), "white")
    panel.paste(qr, (40, 40))
    img.paste(panel, ((W - 700) // 2, 1200))
    d.text((W // 2, 2000), data["name"], font=font(64, True), fill="white", anchor="mm")
    d.text((W // 2, 2090), f"Blood group {data['blood_group']}", font=font(52), fill="white", anchor="mm")
    if data["allergies"]:
        txt = "Allergic to " + ", ".join(a["substance"] for a in data["allergies"])
        d.rounded_rectangle((120, 2160, W - 120, 2260), radius=24, fill=(180, 35, 24))
        d.text((W // 2, 2210), txt[:40], font=font(44, True), fill="white", anchor="mm")
    out = io.BytesIO()
    img.save(out, format="PNG")
    return out.getvalue()
