"""Generate the synthetic demo documents described in docs/SPEC.md §15.

    python -m scripts.generate_demo_docs

Writes to <repo>/demo_data/{rajan,lakshmi}/. Output is deterministic (fixed seeds,
reportlab invariant mode), so file hashes are stable across runs. That matters
because DEMO_CACHE is keyed by sha256. All people and organisations are fictional.
"""

import functools
import io
import math
import random
from datetime import date
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont
from reportlab import rl_config
from reportlab.lib.colors import HexColor, white
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen.canvas import Canvas

from app.config import get_settings

rl_config.invariant = 1  # no timestamps / random IDs in the PDF → stable sha256

ASSETS = Path(__file__).parent / "assets" / "fonts"
W, H = A4
FOOTNOTE = "Synthetic demo document generated for HealthThread. Not a real patient or organisation."

RAJAN = {"name": "Rajan Subramanian", "dob": date(1962, 5, 14), "sex": "Male"}
LAKSHMI = {"name": "Lakshmi Iyer", "dob": date(1968, 3, 9), "sex": "Female"}


class FileCanvas(Canvas):
    """Renders in memory, then writes bytes. Writing via a filename makes reportlab
    derive the PDF /ID from the path, which would change the hash per checkout."""

    def __init__(self, path: Path) -> None:
        self._out_path = path
        self._buffer = io.BytesIO()
        super().__init__(self._buffer, pagesize=A4)

    def save(self) -> None:
        super().save()
        self._out_path.write_bytes(self._buffer.getvalue())


def age_at(dob: date, on: date) -> int:
    return on.year - dob.year - ((on.month, on.day) < (dob.month, dob.day))


def footnote(c: Canvas, y: float = 22) -> None:
    c.setFont("Helvetica-Oblique", 6.5)
    c.setFillColor(HexColor("#9E9E9E"))
    c.drawCentredString(W / 2, y, FOOTNOTE)


def wrap(c: Canvas, text: str, font: str, size: float, width: float) -> list[str]:
    words, lines, cur = text.split(), [], ""
    for w in words:
        trial = f"{cur} {w}".strip()
        if c.stringWidth(trial, font, size) <= width:
            cur = trial
        else:
            lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines


def para(c: Canvas, x: float, y: float, text: str, font: str, size: float, width: float, leading: float) -> float:
    c.setFont(font, size)
    for line in wrap(c, text, font, size, width):
        c.drawString(x, y, line)
        y -= leading
    return y


# ─────────────────────────────── Sunrise (formal, blue letterhead) ──────────────────────────────

SUN_BLUE = HexColor("#1F4E8C")
SUN_LIGHT = HexColor("#E8EEF7")


def sunrise_letterhead(c: Canvas, dept: str) -> float:
    c.setFillColor(SUN_BLUE)
    c.rect(0, H - 8, W, 8, fill=1, stroke=0)
    # Emblem: sun over a horizon
    c.setStrokeColor(SUN_BLUE)
    c.setFillColor(SUN_BLUE)
    c.circle(62, H - 58, 16, fill=1, stroke=0)
    c.setFillColor(white)
    c.rect(40, H - 74, 44, 14, fill=1, stroke=0)
    c.setFillColor(SUN_BLUE)
    for i in range(7):
        a = math.pi * (i + 1) / 8
        c.setLineWidth(1.6)
        c.line(62 + 20 * math.cos(a), H - 58 + 20 * math.sin(a), 62 + 27 * math.cos(a), H - 58 + 27 * math.sin(a))
    c.rect(36, H - 62, 52, 1.5, fill=1, stroke=0)

    c.setFont("Times-Bold", 17)
    c.drawString(100, H - 50, "SUNRISE DIABETES & MULTISPECIALITY HOSPITAL")
    c.setFont("Times-Italic", 10)
    c.setFillColor(HexColor("#37474F"))
    c.drawString(100, H - 64, "Diabetes  ·  Endocrinology  ·  Nephrology  ·  Internal Medicine")
    c.setFont("Times-Roman", 8.5)
    c.drawString(
        100,
        H - 76,
        "No. 14, Lake View Road, Mylapore, Chennai – 600 004   |   Tel: 044-2499 1234   |   NABH Accredited",
    )
    c.setStrokeColor(SUN_BLUE)
    c.setLineWidth(1.4)
    c.line(36, H - 88, W - 36, H - 88)
    c.setLineWidth(0.5)
    c.line(36, H - 91, W - 36, H - 91)
    c.setFont("Times-Bold", 11.5)
    c.setFillColor(SUN_BLUE)
    c.drawCentredString(W / 2, H - 110, dept)
    return H - 122


def sunrise_patient_box(c: Canvas, y: float, rows: list[tuple[str, str, str, str]]) -> float:
    row_h = 17
    c.setStrokeColor(HexColor("#90A4C3"))
    c.setLineWidth(0.6)
    c.setFillColor(SUN_LIGHT)
    c.rect(36, y - row_h * len(rows), W - 72, row_h * len(rows), fill=1, stroke=1)
    for i, (k1, v1, k2, v2) in enumerate(rows):
        yy = y - row_h * (i + 1) + 5
        c.setFillColor(HexColor("#263238"))
        c.setFont("Times-Bold", 9.5)
        c.drawString(44, yy, k1)
        c.drawString(310, yy, k2)
        c.setFont("Times-Roman", 9.5)
        c.drawString(130, yy, v1)
        c.drawString(390, yy, v2)
        if i:
            c.line(36, y - row_h * i, W - 36, y - row_h * i)
    return y - row_h * len(rows) - 18


def sunrise_heading(c: Canvas, y: float, text: str) -> float:
    c.setFont("Times-Bold", 11)
    c.setFillColor(SUN_BLUE)
    c.drawString(40, y, text)
    c.setFillColor(HexColor("#212121"))
    return y - 15


def sunrise_opd(path: Path) -> None:
    d = date(2024, 3, 12)
    c = FileCanvas(path)
    c.setTitle("Sunrise OPD consultation")
    y = sunrise_letterhead(c, "OUT-PATIENT CONSULTATION RECORD")
    y = sunrise_patient_box(
        c,
        y,
        [
            ("Patient Name:", f"Mr. {RAJAN['name']}", "UHID:", "SDH/24/018733"),
            ("Age / Sex:", f"{age_at(RAJAN['dob'], d)} Y / {RAJAN['sex']}", "Date:", "12-Mar-2024"),
            ("Consultant:", "Dr. K. Srinivasan, MD, DM", "Department:", "Diabetology"),
        ],
    )
    y = sunrise_heading(c, y, "Presenting Complaints")
    y = (
        para(
            c,
            52,
            y,
            "Increased thirst and frequent urination for 2 months. Generalised fatigue.",
            "Times-Roman",
            10.5,
            W - 110,
            14,
        )
        - 6
    )
    y = sunrise_heading(c, y, "Known Drug Allergy")
    c.setFillColor(HexColor("#FDECEA"))
    c.setStrokeColor(HexColor("#C62828"))
    c.rect(48, y - 8, 300, 20, fill=1, stroke=1)
    c.setFillColor(HexColor("#B71C1C"))
    c.setFont("Times-Bold", 10.5)
    c.drawString(56, y - 1, "ALLERGY: Penicillin — skin rash (2022)")
    y -= 30
    y = sunrise_heading(c, y, "Examination")
    y = (
        para(
            c,
            52,
            y,
            "Wt 78 kg, BMI 27.4 kg/m². BP 132/84 mmHg, PR 78/min. CVS, RS: NAD. Feet: sensation intact.",
            "Times-Roman",
            10.5,
            W - 110,
            14,
        )
        - 6
    )
    y = sunrise_heading(c, y, "Investigations")
    y = (
        para(
            c,
            52,
            y,
            "HbA1c 7.8 % (12-Mar-2024). Detailed laboratory report enclosed separately.",
            "Times-Roman",
            10.5,
            W - 110,
            14,
        )
        - 6
    )
    y = sunrise_heading(c, y, "Diagnosis")
    c.setFont("Times-Bold", 10.5)
    c.drawString(52, y, "Type 2 diabetes mellitus (E11.9)")
    y -= 24

    # Prescription table
    c.setFont("Times-Bold", 22)
    c.setFillColor(SUN_BLUE)
    c.drawString(40, y - 6, "Rx")
    y -= 14
    cols = [70, 260, 340, 440]
    headers = ["Medicine", "Dosage", "When", "Duration"]
    c.setFillColor(SUN_LIGHT)
    c.rect(64, y - 16, W - 100, 16, fill=1, stroke=0)
    c.setFillColor(HexColor("#263238"))
    c.setFont("Times-Bold", 9.5)
    for x, h in zip(cols, headers, strict=True):
        c.drawString(x, y - 11, h)
    y -= 32
    c.setFont("Times-Roman", 10.5)
    for x, v in zip(cols, ["1. Tab. Glycomet 500 mg", "1 – 0 – 1", "After food", "To continue"], strict=True):
        c.drawString(x, y, v)
    c.setStrokeColor(HexColor("#B0BEC5"))
    c.line(64, y - 8, W - 36, y - 8)
    y -= 34
    y = sunrise_heading(c, y, "Advice")
    y = para(
        c,
        52,
        y,
        "Diabetic diet; 30 minutes brisk walk daily. Home glucose monitoring. Review after 3 months with HbA1c, "
        "fasting blood sugar and renal function.",
        "Times-Roman",
        10.5,
        W - 110,
        14,
    )
    # Signature
    c.setFont("Times-Italic", 14)
    c.setFillColor(HexColor("#0D2B5E"))
    c.drawRightString(W - 50, 150, "K. Srinivasan")
    c.setFont("Times-Bold", 10)
    c.setFillColor(HexColor("#212121"))
    c.drawRightString(W - 50, 134, "Dr. K. Srinivasan")
    c.setFont("Times-Roman", 8.5)
    c.drawRightString(W - 50, 122, "MD, DM (Endocrinology) · Reg. No. TNMC 31877")
    c.setStrokeColor(SUN_BLUE)
    c.line(36, 60, W - 36, 60)
    c.setFont("Times-Roman", 7.5)
    c.setFillColor(HexColor("#607D8B"))
    c.drawCentredString(W / 2, 48, "Emergency: 044-2499 1000 (24×7)   ·   Please bring this record on your next visit.")
    footnote(c)
    c.showPage()
    c.save()


def sunrise_lab(path: Path) -> None:
    d = date(2024, 3, 12)
    c = FileCanvas(path)
    c.setTitle("Sunrise laboratory report")
    y = sunrise_letterhead(c, "DEPARTMENT OF LABORATORY MEDICINE — BIOCHEMISTRY REPORT")
    y = sunrise_patient_box(
        c,
        y,
        [
            ("Patient Name:", f"Mr. {RAJAN['name']}", "UHID:", "SDH/24/018733"),
            ("Age / Sex:", f"{age_at(RAJAN['dob'], d)} Y / {RAJAN['sex']}", "Ref. By:", "Dr. K. Srinivasan"),
            ("Collected:", "12-Mar-2024 08:15", "Reported:", "12-Mar-2024 14:30"),
        ],
    )
    cols = [44, 270, 340, 420]
    c.setFillColor(SUN_BLUE)
    c.rect(36, y - 18, W - 72, 18, fill=1, stroke=0)
    c.setFillColor(white)
    c.setFont("Times-Bold", 9.5)
    for x, h in zip(cols, ["TEST NAME", "RESULT", "UNITS", "BIOLOGICAL REF. INTERVAL"], strict=True):
        c.drawString(x, y - 13, h)
    y -= 38
    rows = [
        ("Glycated Haemoglobin (HbA1c)", "7.8", "H", "%", "4.0 - 5.6"),
        ("Fasting Blood Sugar", "156", "H", "mg/dL", "70 - 100"),
        ("Serum Creatinine", "1.0", "", "mg/dL", "0.7 - 1.3"),
        ("eGFR", "72", "", "mL/min/1.73m²", "> 60"),
    ]
    for name, val, flag, unit, ref in rows:
        c.setFillColor(HexColor("#212121"))
        c.setFont("Times-Roman", 10.5)
        c.drawString(cols[0], y, name)
        c.setFont("Times-Bold" if flag else "Times-Roman", 10.5)
        c.drawString(cols[1], y, f"{val} {flag}".strip())
        c.setFont("Times-Roman", 10.5)
        c.drawString(cols[2], y, unit)
        c.drawString(cols[3], y, ref)
        c.setStrokeColor(HexColor("#CFD8DC"))
        c.line(36, y - 7, W - 36, y - 7)
        y -= 24
    y -= 6
    c.setFont("Times-Italic", 8.5)
    c.setFillColor(HexColor("#546E7A"))
    c.drawString(
        44,
        y,
        "eGFR calculated by CKD-EPI equation. HbA1c by HPLC (NGSP certified). H = above reference interval.",
    )
    c.setFont("Times-Bold", 9)
    c.drawCentredString(W / 2, y - 26, "*** End of Report ***")
    c.setFont("Times-Italic", 13)
    c.setFillColor(HexColor("#0D2B5E"))
    c.drawRightString(W - 50, 150, "Anitha Rao")
    c.setFont("Times-Bold", 10)
    c.setFillColor(HexColor("#212121"))
    c.drawRightString(W - 50, 134, "Dr. Anitha Rao")
    c.setFont("Times-Roman", 8.5)
    c.drawRightString(W - 50, 122, "MD (Pathology) · Consultant Pathologist")
    footnote(c)
    c.showPage()
    c.save()


# ─────────────────────────────── Lakeview (modern two-column, red) ──────────────────────────────

LV_RED = HexColor("#C62828")
LV_SIDEBAR = HexColor("#FBEDEC")
LV_INK = HexColor("#1E1E24")
SIDEBAR_W = 178


def lakeview_frame(c: Canvas, title: str, side_rows: list[tuple[str, str]]) -> float:
    c.setFillColor(LV_SIDEBAR)
    c.rect(0, 0, SIDEBAR_W, H, fill=1, stroke=0)
    c.setFillColor(LV_RED)
    c.rect(0, H - 120, SIDEBAR_W, 120, fill=1, stroke=0)
    # Heart-line logo
    c.setStrokeColor(white)
    c.setLineWidth(2.2)
    p = c.beginPath()
    pts = [(22, H - 44), (46, H - 44), (54, H - 30), (64, H - 62), (74, H - 38), (80, H - 44), (104, H - 44)]
    p.moveTo(*pts[0])
    for pt in pts[1:]:
        p.lineTo(*pt)
    c.drawPath(p, stroke=1, fill=0)
    c.setFillColor(white)
    c.setFont("Helvetica-Bold", 19)
    c.drawString(22, H - 86, "LAKEVIEW")
    c.setFont("Helvetica", 10)
    c.drawString(22, H - 102, "HEART INSTITUTE")
    y = H - 150
    for label, value in side_rows:
        c.setFont("Helvetica-Bold", 7)
        c.setFillColor(LV_RED)
        c.drawString(22, y, label.upper())
        c.setFont("Helvetica", 9.5)
        c.setFillColor(LV_INK)
        for line in wrap(c, value, "Helvetica", 9.5, SIDEBAR_W - 34):
            y -= 13
            c.drawString(22, y, line)
        y -= 20
    c.setFont("Helvetica", 7.5)
    c.setFillColor(HexColor("#6D6D73"))
    for i, line in enumerate(
        ["21 Lakeview Drive, Hebbal", "Bengaluru 560 024", "+91 80 4111 2200", "lakeviewheart.example"]
    ):
        c.drawString(22, 80 - i * 11, line)
    c.setFillColor(LV_INK)
    c.setFont("Helvetica-Bold", 21)
    c.drawString(SIDEBAR_W + 30, H - 64, title)
    c.setFillColor(LV_RED)
    c.rect(SIDEBAR_W + 30, H - 76, 46, 3, fill=1, stroke=0)
    return H - 108


def lv_section(c: Canvas, y: float, label: str, body: str | None = None) -> float:
    x = SIDEBAR_W + 30
    c.setFont("Helvetica-Bold", 8)
    c.setFillColor(LV_RED)
    c.drawString(x, y, label.upper())
    y -= 15
    if body:
        c.setFillColor(LV_INK)
        y = para(c, x, y, body, "Helvetica", 10, W - x - 36, 14)
        y -= 12
    return y


def lakeview_cardiology(path: Path) -> None:
    d = date(2025, 1, 20)
    c = FileCanvas(path)
    c.setTitle("Lakeview cardiology consultation")
    y = lakeview_frame(
        c,
        "Cardiology Consultation",
        [
            ("Patient", RAJAN["name"]),
            ("Age / Sex", f"{age_at(RAJAN['dob'], d)} · {RAJAN['sex']}"),
            ("MRN", "LHI-0098812"),
            ("Visit date", "20 Jan 2025"),
            ("Consultant", "Dr. S. Fernandes, DM (Cardiology)"),
        ],
    )
    y = lv_section(c, y, "Presenting concern", "Morning headaches for 3 weeks. BP in the 160s at a pharmacy check.")
    y = lv_section(
        c,
        y,
        "Examination",
        "BP 158/96 mmHg (sitting, repeated after 5 min). HR 82/min, regular. S1 S2 normal, no murmurs. "
        "No pedal oedema.",
    )
    y = lv_section(c, y, "ECG", "Normal sinus rhythm. No LVH by voltage criteria.")
    y = lv_section(c, y, "Impression")
    c.setFont("Helvetica-Bold", 11)
    c.setFillColor(LV_INK)
    c.drawString(SIDEBAR_W + 30, y, "Essential hypertension (I10)")
    y -= 30
    y = lv_section(c, y, "Medications started")
    x0 = SIDEBAR_W + 30
    cols = [x0, x0 + 130, x0 + 190, x0 + 250]
    c.setFillColor(HexColor("#F4F4F6"))
    c.rect(x0 - 6, y - 6, W - x0 - 30, 18, fill=1, stroke=0)
    c.setFillColor(HexColor("#6D6D73"))
    c.setFont("Helvetica-Bold", 8)
    for x, h in zip(cols, ["MEDICINE", "DOSE", "SCHEDULE", "NOTES"], strict=True):
        c.drawString(x, y, h)
    y -= 22
    for row in [
        ("Tab. Cardace", "5 mg", "1-0-0", "Morning"),
        ("Tab. Ecosprin", "75 mg", "0-1-0", "After lunch"),
    ]:
        c.setFont("Helvetica", 10)
        c.setFillColor(LV_INK)
        for x, v in zip(cols, row, strict=True):
            c.drawString(x, y, v)
        c.setStrokeColor(HexColor("#E3E3E8"))
        c.line(x0 - 6, y - 7, W - 36, y - 7)
        y -= 22
    y -= 12
    y = lv_section(
        c,
        y,
        "Plan",
        "Home BP log twice daily. Low-salt diet. Review in 6 weeks with renal function and electrolytes.",
    )
    c.setFont("Helvetica-Oblique", 13)
    c.setFillColor(HexColor("#5A1010"))
    c.drawString(SIDEBAR_W + 30, 140, "S. Fernandes")
    c.setStrokeColor(LV_INK)
    c.line(SIDEBAR_W + 30, 134, SIDEBAR_W + 200, 134)
    c.setFont("Helvetica-Bold", 9)
    c.setFillColor(LV_INK)
    c.drawString(SIDEBAR_W + 30, 122, "Dr. S. Fernandes")
    c.setFont("Helvetica", 8)
    c.drawString(SIDEBAR_W + 30, 111, "Consultant Cardiologist · KMC Reg. 66104")
    footnote(c)
    c.showPage()
    c.save()


def lakeview_lab(path: Path) -> None:
    c = FileCanvas(path)
    c.setTitle("Lakeview laboratory report")
    y = lakeview_frame(
        c,
        "Laboratory Report",
        [
            ("Patient", RAJAN["name"]),
            ("Age / Sex", f"{age_at(RAJAN['dob'], date(2025, 1, 20))} · {RAJAN['sex']}"),
            ("MRN", "LHI-0098812"),
            ("Sample collected", "20 Jan 2025, 09:05"),
            ("Requested by", "Dr. S. Fernandes"),
        ],
    )
    x0 = SIDEBAR_W + 30
    cols = [x0, x0 + 170, x0 + 225, x0 + 315]
    c.setFont("Helvetica-Bold", 8)
    c.setFillColor(HexColor("#6D6D73"))
    for x, h in zip(cols, ["INVESTIGATION", "RESULT", "UNIT", "REFERENCE"], strict=True):
        c.drawString(x, y, h)
    y -= 12
    rows = [
        ("Creatinine, Serum", "1.2", "mg/dL", "0.7 – 1.3", False),
        ("Estimated GFR (CKD-EPI)", "61", "mL/min/1.73m²", "> 60", False),
        ("HbA1c", "7.2", "%", "4.0 – 5.6", True),
        ("Potassium", "4.6", "mmol/L", "3.5 – 5.1", False),
    ]
    for i, (name, val, unit, ref, high) in enumerate(rows):
        if i % 2 == 0:
            c.setFillColor(HexColor("#F7F7F9"))
            c.rect(x0 - 8, y - 22, W - x0 - 28, 26, fill=1, stroke=0)
        c.setFillColor(LV_INK)
        c.setFont("Helvetica", 10)
        c.drawString(cols[0], y - 13, name)
        c.setFont("Helvetica-Bold", 10)
        c.setFillColor(LV_RED if high else LV_INK)
        c.drawString(cols[1], y - 13, val)
        c.setFillColor(LV_INK)
        c.setFont("Helvetica", 9.5)
        c.drawString(cols[2], y - 13, unit)
        c.drawString(cols[3], y - 13, ref)
        y -= 26
    y -= 20
    c.setFont("Helvetica-Oblique", 8.5)
    c.setFillColor(HexColor("#6D6D73"))
    y = para(
        c,
        x0,
        y,
        "eGFR calculated with the CKD-EPI 2021 creatinine equation. Values in red are outside the reference range.",
        "Helvetica-Oblique",
        8.5,
        W - x0 - 36,
        12,
    )
    c.setFont("Helvetica-Bold", 9)
    c.setFillColor(LV_INK)
    c.drawString(x0, 122, "Dr. P. Menon")
    c.setFont("Helvetica", 8)
    c.drawString(x0, 111, "MD (Biochemistry) · Laboratory Director")
    footnote(c)
    c.showPage()
    c.save()


# ─────────────────────────────── City Diagnostics (table-style, green) ──────────────────────────

CD_GREEN = HexColor("#1B5E20")
CD_GRID = HexColor("#7A9A7E")


def citydx_lab(path: Path) -> None:
    d = date(2026, 1, 15)
    c = FileCanvas(path)
    c.setTitle("City Diagnostics report")
    x0, x1 = 30, W - 30
    top = H - 30
    c.setStrokeColor(CD_GRID)
    c.setLineWidth(0.8)
    # Header grid cell
    c.rect(x0, top - 70, x1 - x0, 70, stroke=1, fill=0)
    c.setFillColor(CD_GREEN)
    c.rect(x0, top - 70, 70, 70, fill=1, stroke=0)
    c.setFillColor(white)
    c.setFont("Helvetica-Bold", 30)
    c.drawCentredString(x0 + 35, top - 46, "CD")
    c.setFillColor(CD_GREEN)
    c.setFont("Courier-Bold", 20)
    c.drawString(x0 + 84, top - 30, "CITY DIAGNOSTICS")
    c.setFont("Courier", 8.5)
    c.setFillColor(HexColor("#33473A"))
    c.drawString(x0 + 84, top - 44, "Pathology | Imaging | Home Collection")
    c.drawString(x0 + 84, top - 56, "Plot 7, Anna Salai, Chennai 600 018 · 1800-425-0007")
    # Fake barcode
    rnd = random.Random(7)
    bx = x1 - 128
    for _ in range(40):
        wbar = rnd.choice([0.8, 1.2, 2.0])
        c.setFillColor(HexColor("#111111"))
        c.rect(bx, top - 50, wbar, 30, fill=1, stroke=0)
        bx += wbar + rnd.choice([0.8, 1.4])
    c.setFont("Courier", 7)
    c.drawString(x1 - 128, top - 60, "SID 26011500417")
    # Patient grid
    y = top - 70
    cells = [
        [("Patient", RAJAN["name"]), ("Sample ID", "26011500417")],
        [("Age / Gender", f"{age_at(RAJAN['dob'], d)} Yrs / M"), ("Collected", "15/01/2026 07:40")],
        [("Referred by", "Self"), ("Reported", "15/01/2026 16:05")],
    ]
    for row in cells:
        c.rect(x0, y - 20, (x1 - x0) / 2, 20, stroke=1, fill=0)
        c.rect(x0 + (x1 - x0) / 2, y - 20, (x1 - x0) / 2, 20, stroke=1, fill=0)
        for j, (k, v) in enumerate(row):
            xx = x0 + j * (x1 - x0) / 2 + 6
            c.setFont("Courier-Bold", 8.5)
            c.setFillColor(CD_GREEN)
            c.drawString(xx, y - 14, f"{k}:")
            c.setFont("Courier", 9)
            c.setFillColor(HexColor("#111111"))
            c.drawString(xx + 95, y - 14, v)
        y -= 20
    y -= 18
    c.setFillColor(CD_GREEN)
    c.rect(x0, y - 20, x1 - x0, 20, fill=1, stroke=0)
    c.setFillColor(white)
    c.setFont("Courier-Bold", 10)
    c.drawCentredString(W / 2, y - 14, "CLINICAL BIOCHEMISTRY")
    y -= 20
    widths = [190, 80, 40, 100, 125]
    heads = ["Test Description", "Value", "Flag", "Unit", "Ref. Range"]
    rows = [
        ("S. Creatinine", "1.4", "H", "mg/dL", "0.7-1.3"),
        ("GFR, estimated", "52", "L", "mL/min/1.73m²", ">60"),
        ("HbA1c", "7.0", "H", "%", "4.0-5.6"),
    ]
    for r_i, row in enumerate([heads, *rows]):
        x = x0
        for w_i, (wid, val) in enumerate(zip(widths, row, strict=True)):
            c.setStrokeColor(CD_GRID)
            c.rect(x, y - 22, wid, 22, stroke=1, fill=0)
            if r_i == 0:
                c.setFont("Courier-Bold", 9)
                c.setFillColor(CD_GREEN)
            else:
                c.setFont("Courier-Bold" if w_i in (1, 2) and row[2] else "Courier", 9.5)
                c.setFillColor(HexColor("#B71C1C") if w_i == 2 else HexColor("#111111"))
            c.drawString(x + 6, y - 15, val)
            x += wid
        y -= 22
    y -= 24
    c.setFont("Courier", 8)
    c.setFillColor(HexColor("#33473A"))
    for line in [
        "Method: Creatinine - Jaffe kinetic (IDMS traceable). eGFR - CKD-EPI 2021.",
        "HbA1c - HPLC, NGSP certified. Flag: H = High, L = Low.",
        "",
        "--------------------------- END OF REPORT ---------------------------",
    ]:
        c.drawString(x0 + 6, y, line)
        y -= 12
    c.setFont("Courier-Bold", 9)
    c.setFillColor(HexColor("#111111"))
    c.drawString(x1 - 210, 120, "Dr. Farhan Qureshi, MD")
    c.setFont("Courier", 8)
    c.drawString(x1 - 210, 109, "Consultant Biochemist")
    footnote(c)
    c.showPage()
    c.save()


# ─────────────────────────────── Medline Path Labs (SI units, purple) ───────────────────────────

ML_PURPLE = HexColor("#4A2C82")


def medline_lab(path: Path) -> None:
    d = date(2026, 8, 5)
    c = FileCanvas(path)
    c.setTitle("Medline Path Labs report")
    c.setFillColor(ML_PURPLE)
    c.circle(W / 2, H - 58, 22, fill=1, stroke=0)
    c.setFillColor(white)
    c.setFont("Helvetica-Bold", 15)
    c.drawCentredString(W / 2, H - 63, "ML")
    c.setFillColor(ML_PURPLE)
    c.setFont("Helvetica-Bold", 18)
    c.drawCentredString(W / 2, H - 102, "Medline Path Labs")
    c.setFont("Helvetica", 9)
    c.setFillColor(HexColor("#5E5873"))
    c.drawCentredString(
        W / 2, H - 116, "Clinical Chemistry  ·  Results in SI units  ·  Coimbatore 641 002  ·  0422-430 9900"
    )
    c.setStrokeColor(ML_PURPLE)
    c.setLineWidth(0.6)
    c.line(60, H - 128, W - 60, H - 128)

    y = H - 152
    info = [
        ("Name", RAJAN["name"], "Lab No.", "ML/26/08/44120"),
        ("Age / Sex", f"{age_at(RAJAN['dob'], d)} years / Male", "Collected", "05.08.2026 08:30"),
        ("Clinician", "Self referral", "Validated", "05.08.2026 13:10"),
    ]
    for k1, v1, k2, v2 in info:
        c.setFont("Helvetica", 8.5)
        c.setFillColor(HexColor("#7C7690"))
        c.drawString(60, y, k1)
        c.drawString(320, y, k2)
        c.setFont("Helvetica-Bold", 9.5)
        c.setFillColor(HexColor("#221C35"))
        c.drawString(130, y, v1)
        c.drawString(390, y, v2)
        y -= 16
    y -= 22
    results = [
        ("Creatinine", "133", "µmol/L", "64 – 104", "HIGH"),
        ("eGFR", "47", "mL/min/1.73m²", "> 60", "LOW"),
        ("Potassium", "5.0", "mmol/L", "3.5 – 5.1", ""),
    ]
    for name, val, unit, ref, flag in results:
        c.setStrokeColor(HexColor("#D9D3EA"))
        c.roundRect(60, y - 40, W - 120, 46, 6, stroke=1, fill=0)
        c.setFont("Helvetica-Bold", 11)
        c.setFillColor(HexColor("#221C35"))
        c.drawString(76, y - 12, name)
        c.setFont("Helvetica", 8.5)
        c.setFillColor(HexColor("#7C7690"))
        c.drawString(76, y - 28, f"Reference interval: {ref} {unit}")
        c.setFont("Helvetica-Bold", 18)
        c.setFillColor(ML_PURPLE if not flag else HexColor("#B3261E"))
        c.drawRightString(W - 170, y - 22, val)
        c.setFont("Helvetica", 9)
        c.setFillColor(HexColor("#5E5873"))
        c.drawString(W - 162, y - 22, unit)
        if flag:
            c.setFont("Helvetica-Bold", 7.5)
            c.setFillColor(HexColor("#B3261E"))
            c.drawRightString(W - 72, y - 8, flag)
        y -= 60
    y -= 6
    c.setFont("Helvetica-Oblique", 8.5)
    c.setFillColor(HexColor("#5E5873"))
    y = para(
        c,
        60,
        y,
        "All results are reported in SI units. To convert creatinine to mg/dL divide by 88.4. "
        "eGFR by CKD-EPI 2021 (race-free). Interpret in clinical context.",
        "Helvetica-Oblique",
        8.5,
        W - 120,
        12,
    )
    c.setFont("Helvetica-Bold", 9)
    c.setFillColor(HexColor("#221C35"))
    c.drawCentredString(W / 2, 120, "Dr. Nirmala Devi, MD (Biochemistry)")
    c.setFont("Helvetica", 8)
    c.drawCentredString(W / 2, 109, "Electronically validated")
    footnote(c)
    c.showPage()
    c.save()


# ─────────────────────────────── Greenfield (Lakshmi's control hospital) ────────────────────────

GF_BROWN = HexColor("#6D4C41")


def greenfield_header(c: Canvas, subtitle: str) -> float:
    c.setFillColor(HexColor("#EFEBE9"))
    c.rect(0, H - 96, W, 96, fill=1, stroke=0)
    c.setFillColor(GF_BROWN)
    c.setFont("Helvetica-Bold", 18)
    c.drawString(40, H - 48, "Greenfield Multispeciality Hospital")
    c.setFont("Helvetica", 9)
    c.setFillColor(HexColor("#5D4037"))
    c.drawString(
        40,
        H - 64,
        "Endocrinology · General Medicine · Women's Health   |   Thrissur, Kerala 680 001   |   0487-233 4455",
    )
    c.setFont("Helvetica-Bold", 11)
    c.setFillColor(GF_BROWN)
    c.drawString(40, H - 120, subtitle)
    return H - 140


def greenfield_patient(c: Canvas, y: float, d: date, extra: str) -> float:
    c.setFont("Helvetica", 9.5)
    c.setFillColor(HexColor("#3E2723"))
    c.drawString(
        40,
        y,
        f"Patient: {LAKSHMI['name']}    Age/Sex: {age_at(LAKSHMI['dob'], d)} / F    Hosp. No: GMH-554120",
    )
    c.drawString(40, y - 14, f"Date: {d.strftime('%d %b %Y')}    {extra}")
    c.setStrokeColor(HexColor("#BCAAA4"))
    c.line(40, y - 24, W - 40, y - 24)
    return y - 46


def greenfield_tsh_table(c: Canvas, y: float, value: str) -> float:
    c.setFont("Helvetica-Bold", 9)
    c.setFillColor(HexColor("#5D4037"))
    for x, h in zip([40, 260, 340, 420], ["Investigation", "Result", "Unit", "Reference"], strict=True):
        c.drawString(x, y, h)
    y -= 18
    c.setFont("Helvetica", 10.5)
    c.setFillColor(HexColor("#212121"))
    for x, v in zip(
        [40, 260, 340, 420], ["TSH (Thyroid Stimulating Hormone)", value, "mIU/L", "0.4 - 4.5"], strict=True
    ):
        c.drawString(x, y, v)
    c.setFont("Helvetica-Oblique", 8)
    c.setFillColor(HexColor("#8D6E63"))
    c.drawString(40, y - 22, "Method: CLIA, 3rd generation. Specimen: serum.")
    return y - 40


def greenfield_opd(path: Path) -> None:
    d = date(2025, 1, 10)
    c = FileCanvas(path)
    c.setTitle("Greenfield OPD note")
    # Page 1: consultation
    y = greenfield_header(c, "Endocrinology OPD — Consultation Note")
    y = greenfield_patient(c, y, d, "Consultant: Dr. Mini Thomas, MD, DM (Endocrinology)")
    for heading, body in [
        (
            "History",
            "Known case of hypothyroidism since 2019, on levothyroxine. Feels well; no palpitations, weight stable.",
        ),
        ("Examination", "Pulse 74/min, BP 122/78 mmHg. Thyroid not palpable. No pedal oedema."),
        ("Investigations", "TSH report of today enclosed (page 2): within target on current dose."),
        ("Diagnosis", "Hypothyroidism (E03.9), euthyroid on treatment."),
    ]:
        c.setFont("Helvetica-Bold", 10)
        c.setFillColor(GF_BROWN)
        c.drawString(40, y, heading)
        c.setFillColor(HexColor("#212121"))
        y = para(c, 40, y - 14, body, "Helvetica", 10, W - 80, 13.5) - 10
    c.setFont("Helvetica-Bold", 16)
    c.setFillColor(GF_BROWN)
    c.drawString(40, y - 4, "Rx")
    c.setFont("Helvetica", 10.5)
    c.setFillColor(HexColor("#212121"))
    c.drawString(80, y - 4, "Tab. Thyronorm 50 mcg    1-0-0    before breakfast (empty stomach)    — continue")
    y -= 36
    y = para(
        c,
        40,
        y,
        "Advice: take tablet 30–45 minutes before food. Repeat TSH in 6–9 months.",
        "Helvetica",
        10,
        W - 80,
        13.5,
    )
    c.setFont("Helvetica-Bold", 9.5)
    c.drawString(W - 220, 130, "Dr. Mini Thomas")
    c.setFont("Helvetica", 8)
    c.drawString(W - 220, 119, "TCMC Reg. 40712")
    c.setFont("Helvetica", 8)
    c.setFillColor(HexColor("#8D6E63"))
    c.drawRightString(W - 40, 40, "Page 1 of 2")
    footnote(c)
    c.showPage()
    # Page 2: attached lab report
    y = greenfield_header(c, "Department of Biochemistry — Thyroid Function")
    y = greenfield_patient(c, y, d, "Sample: 10 Jan 2025 08:20    Ref: Dr. Mini Thomas")
    greenfield_tsh_table(c, y, "2.1")
    c.setFont("Helvetica", 8)
    c.setFillColor(HexColor("#8D6E63"))
    c.drawRightString(W - 40, 40, "Page 2 of 2")
    footnote(c)
    c.showPage()
    c.save()


def greenfield_lab(path: Path, d: date, tsh: str) -> None:
    c = FileCanvas(path)
    c.setTitle("Greenfield thyroid report")
    y = greenfield_header(c, "Department of Biochemistry — Thyroid Function")
    y = greenfield_patient(c, y, d, f"Sample: {d.strftime('%d %b %Y')} 08:10    Ref: Dr. Mini Thomas")
    greenfield_tsh_table(c, y, tsh)
    footnote(c)
    c.showPage()
    c.save()


# ─────────────────────────────── Anand Family Clinic (handwritten PNG) ──────────────────────────

INK = (28, 46, 128)
PRINT_INK = (24, 78, 92)


@functools.lru_cache(maxsize=512)
def _font(name: str, size: int, weight: str | int | None = None) -> ImageFont.FreeTypeFont:
    f = ImageFont.truetype(str(ASSETS / name), size)
    if isinstance(weight, int):
        f.set_variation_by_axes([weight])
    elif weight:
        f.set_variation_by_name(weight)
    return f


def _hand(draw: ImageDraw.ImageDraw, rnd: random.Random, xy: tuple[int, int], text: str, size: int = 54) -> None:
    """Draw handwriting word by word with slight baseline wobble and size variation."""
    x, y = xy
    for word in text.split(" "):
        f = _font("Caveat.ttf", size + rnd.randint(-2, 3), rnd.randint(470, 580))
        draw.text((x, y + rnd.randint(-3, 3)), word, font=f, fill=INK)
        x += int(draw.textlength(word + " ", font=f)) + rnd.randint(-2, 4)


def anand_rx(path: Path, d: date, complaint: list[str], rx: list[str], seed: int) -> None:
    rnd = random.Random(seed)
    w, h = 1240, 1700
    img = Image.new("RGB", (w, h), (250, 247, 236))
    draw = ImageDraw.Draw(img)
    # Paper texture: faint fibres
    for _ in range(1400):
        x, y = rnd.randrange(w), rnd.randrange(h)
        shade = rnd.randint(228, 242)
        draw.line([(x, y), (x + rnd.randint(-6, 6), y + rnd.randint(-6, 6))], fill=(shade, shade - 3, shade - 12))

    # Printed pad header
    serif_b = _font("Lora.ttf", 52, "Bold")
    serif = _font("Lora.ttf", 28, "Regular")
    serif_s = _font("Lora.ttf", 23, "Regular")
    draw.text((80, 70), "Dr. R. ANAND", font=serif_b, fill=PRINT_INK)
    draw.text((80, 134), "M.B.B.S., General Physician", font=serif, fill=PRINT_INK)
    draw.text((80, 172), "Reg. No. TNMC 45120", font=serif_s, fill=PRINT_INK)
    draw.text((w - 80, 76), "ANAND FAMILY CLINIC", font=_font("Lora.ttf", 34, "Bold"), fill=PRINT_INK, anchor="ra")
    draw.text((w - 80, 124), "12, Gandhi Street, Adyar", font=serif_s, fill=PRINT_INK, anchor="ra")
    draw.text((w - 80, 154), "Chennai – 600 020", font=serif_s, fill=PRINT_INK, anchor="ra")
    draw.text((w - 80, 184), "Ph: 98410 22334", font=serif_s, fill=PRINT_INK, anchor="ra")
    draw.line([(70, 228), (w - 70, 228)], fill=PRINT_INK, width=4)
    draw.line([(70, 236), (w - 70, 236)], fill=PRINT_INK, width=1)

    # Printed form labels with handwritten values
    label = _font("Lora.ttf", 26, "Regular")
    draw.text((80, 290), "Name:", font=label, fill=PRINT_INK)
    draw.line([(170, 322), (760, 322)], fill=(150, 160, 170), width=1)
    draw.text((800, 290), "Date:", font=label, fill=PRINT_INK)
    draw.line([(880, 322), (w - 80, 322)], fill=(150, 160, 170), width=1)
    draw.text((80, 360), "Age/Sex:", font=label, fill=PRINT_INK)
    draw.line([(200, 392), (520, 392)], fill=(150, 160, 170), width=1)
    _hand(draw, rnd, (190, 268), "Rajan S.", 56)
    _hand(draw, rnd, (895, 268), f"{d.day}/{d.month}/{d.year}", 54)
    _hand(draw, rnd, (215, 338), f"{age_at(RAJAN['dob'], d)} / M", 54)

    y = 450
    for line in complaint:
        _hand(draw, rnd, (110, y), line, 56)
        y += 78
    # Printed Rx symbol
    draw.text((80, y + 20), "Rx", font=_font("Lora.ttf", 64, "Bold"), fill=PRINT_INK)
    y += 120
    for line in rx:
        _hand(draw, rnd, (150 + rnd.randint(-6, 6), y), line, 60)
        y += 92
    # Signature
    _hand(draw, rnd, (w - 420, h - 330), "R. Anand", 64)
    pts = [(w - 430 + i * 12, h - 248 + int(6 * math.sin(i / 2))) for i in range(28)]
    draw.line(pts, fill=INK, width=3)
    # Printed footer
    draw.line([(70, h - 150), (w - 70, h - 150)], fill=PRINT_INK, width=2)
    draw.text(
        (w // 2, h - 120),
        "Timings: 9 am – 1 pm  ·  5 pm – 9 pm   (Sunday holiday)",
        font=serif_s,
        fill=PRINT_INK,
        anchor="ma",
    )
    draw.text((w // 2, h - 70), FOOTNOTE, font=_font("Lora.ttf", 16, "Regular"), fill=(150, 150, 150), anchor="ma")

    # Phone-photo feel: slight rotation, soft blur, sensor noise, uneven lighting.
    img = img.rotate(rnd.uniform(-1.6, 1.6), resample=Image.Resampling.BICUBIC, expand=True, fillcolor=(236, 232, 220))
    img = img.filter(ImageFilter.GaussianBlur(0.6))
    # Seeded noise (PIL's effect_noise uses an unseeded C RNG, which breaks determinism).
    grain = np.random.default_rng(seed).normal(128, 10, (img.size[1], img.size[0])).clip(0, 255)
    noise = Image.fromarray(grain.astype(np.uint8), mode="L").convert("RGB")
    img = Image.blend(img, noise, 0.06)
    shade = Image.linear_gradient("L").resize(img.size).rotate(25)
    img = Image.composite(img, Image.new("RGB", img.size, (205, 200, 188)), shade.point(lambda v: 200 + v // 5))
    img.save(path, format="PNG", compress_level=6)


# ─────────────────────────────── main ───────────────────────────────────────────────────────────


def generate(out_dir: Path | None = None) -> list[Path]:
    out = out_dir or get_settings().demo_data_dir
    rajan, lakshmi = out / "rajan", out / "lakshmi"
    rajan.mkdir(parents=True, exist_ok=True)
    lakshmi.mkdir(parents=True, exist_ok=True)
    files: list[Path] = []

    def make(fn, path: Path, *args) -> None:
        fn(path, *args)
        files.append(path)

    make(sunrise_opd, rajan / "sunrise_2024-03-12_opd.pdf")
    make(sunrise_lab, rajan / "sunrise_2024-03-12_lab.pdf")
    make(lakeview_cardiology, rajan / "lakeview_2025-01-20_cardiology.pdf")
    make(lakeview_lab, rajan / "lakeview_2025-01-20_lab.pdf")
    make(
        anand_rx,
        rajan / "anand_2025-04-02_rx.png",
        date(2025, 4, 2),
        ["C/o dry cough x 6 wks", "No fever. Chest clear."],
        ["Syp. Dextromethorphan 10 ml", "1-1-1  x 7 days"],
        5,
    )
    make(
        anand_rx,
        rajan / "anand_2025-09-10_rx.png",
        date(2025, 9, 10),
        ["C/o tiredness, high sugars"],
        ["Tab. Glucophage 500 mg", "1-0-1", "Review 1 month"],
        6,
    )
    make(citydx_lab, rajan / "citydx_2026-01-15_lab.pdf")
    make(
        anand_rx,
        rajan / "anand_2026-02-18_rx.png",
        date(2026, 2, 18),
        ["C/o sore throat, fever x 2 days", "Throat congested. T 100.4 F"],
        ["Cap. Novamox 500 mg  1-1-1 x 5 days", "Tab. Dolo 650  SOS"],
        8,
    )
    make(medline_lab, rajan / "medline_2026-08-05_lab.pdf")

    make(greenfield_opd, lakshmi / "greenfield_2025-01-10_opd.pdf")
    make(greenfield_lab, lakshmi / "greenfield_2025-09-22_lab.pdf", date(2025, 9, 22), "2.4")
    make(greenfield_lab, lakshmi / "greenfield_2026-07-14_lab.pdf", date(2026, 7, 14), "1.9")
    return files


if __name__ == "__main__":
    for f in generate():
        print(f"wrote {f.relative_to(get_settings().demo_data_dir.parent)}")
