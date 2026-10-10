"""Render document pages to PNG, optionally highlighting (and cropping to) a snippet."""

import io
import re

import pymupdf
from PIL import Image, ImageDraw


def _find_rects(page: pymupdf.Page, snippet: str) -> list[pymupdf.Rect]:
    """Search the page text for the snippet; fall back to its longest distinctive fragments."""
    text = re.sub(r"\s+", " ", snippet).strip()
    if not text:
        return []
    hits = page.search_for(text)
    if hits:
        return hits
    # Snippets are model-quoted and may differ slightly; try fragments of 4+ words, then key tokens.
    words = text.split(" ")
    for size in (6, 4, 3):
        for i in range(0, max(1, len(words) - size + 1)):
            frag = " ".join(words[i : i + size])
            if len(frag) >= 8 and (hits := page.search_for(frag)):
                return hits
    tokens = sorted({w for w in words if len(w) >= 5 or any(c.isdigit() for c in w)}, key=len, reverse=True)
    for t in tokens[:3]:
        if hits := page.search_for(t):
            return hits[:1]
    return []


def render_page(
    data: bytes, mime: str, page_no: int, *, highlight: str | None = None, crop: bool = False, dpi: int = 110
) -> tuple[bytes, bool]:
    """Return (png_bytes, highlighted). page_no is 1-based."""
    if mime != "application/pdf":
        img = Image.open(io.BytesIO(data)).convert("RGB")
        img.thumbnail((1400, 1800))
        out = io.BytesIO()
        img.save(out, format="PNG", optimize=False)
        return out.getvalue(), False

    with pymupdf.open(stream=data, filetype="pdf") as doc:
        if not 1 <= page_no <= doc.page_count:
            raise ValueError("page out of range")
        page = doc[page_no - 1]
        rects = _find_rects(page, highlight) if highlight else []
        zoom = dpi / 72
        clip = None
        if crop and rects:
            box = pymupdf.Rect(rects[0])
            for r in rects[1:]:
                box |= r
            clip = pymupdf.Rect(0, max(0, box.y0 - 70), page.rect.width, min(page.rect.height, box.y1 + 70))
        pix = page.get_pixmap(matrix=pymupdf.Matrix(zoom, zoom), clip=clip)
        img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
        if rects:
            overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
            draw = ImageDraw.Draw(overlay)
            ox, oy = (clip.x0, clip.y0) if clip else (0, 0)
            for r in rects:
                x0, y0, x1, y1 = ((r.x0 - ox) * zoom, (r.y0 - oy) * zoom, (r.x1 - ox) * zoom, (r.y1 - oy) * zoom)
                draw.rectangle((x0 - 3, y0 - 2, x1 + 3, y1 + 2), fill=(250, 204, 21, 90), outline=(202, 138, 4, 255))
            img = Image.alpha_composite(img.convert("RGBA"), overlay).convert("RGB")
        out = io.BytesIO()
        img.save(out, format="PNG")
        return out.getvalue(), bool(rects)
