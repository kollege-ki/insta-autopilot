"""Rendert ein Karussell (post.json) zu JPEG-Slides im Format 1080x1350 (4:5)."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

W, H = 1080, 1350
PAD = 96

FONT_DIRS = [
    Path("/usr/share/fonts/opentype/inter"),
    Path("/usr/share/fonts/truetype/inter"),
    Path(__file__).resolve().parent.parent / "assets" / "fonts",
]
FONT_FILES = {
    "bold": ["Inter-Bold.otf", "Inter-Bold.ttf", "DejaVuSans-Bold.ttf"],
    "semibold": ["Inter-SemiBold.otf", "Inter-SemiBold.ttf", "DejaVuSans-Bold.ttf"],
    "regular": ["Inter-Regular.otf", "Inter-Regular.ttf", "DejaVuSans.ttf"],
    "mono": ["DejaVuSansMono.ttf"],
}
FALLBACK_DIRS = [Path("/usr/share/fonts/truetype/dejavu")]
_font_cache: dict = {}


def font(kind: str, size: int) -> ImageFont.FreeTypeFont:
    key = (kind, size)
    if key in _font_cache:
        return _font_cache[key]
    for name in FONT_FILES[kind]:
        for d in FONT_DIRS + FALLBACK_DIRS:
            p = d / name
            if p.exists():
                _font_cache[key] = ImageFont.truetype(str(p), size)
                return _font_cache[key]
    raise SystemExit("Keine Schrift gefunden – im Workflow wird 'fonts-inter' installiert.")


def hex_to_rgb(h: str) -> tuple[int, int, int]:
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def wrap(draw: ImageDraw.ImageDraw, text: str, f, max_w: int) -> list[str]:
    lines: list[str] = []
    for para in text.split("\n"):
        words = para.split()
        if not words:
            lines.append("")
            continue
        cur = words[0]
        for w in words[1:]:
            test = f"{cur} {w}"
            if draw.textlength(test, font=f) <= max_w:
                cur = test
            else:
                lines.append(cur)
                cur = w
        lines.append(cur)
    return lines


def fit(draw, text, kind, max_w, max_h, start, minimum, spacing=1.2):
    """Größte Schriftgröße, bei der der Text in die Box passt."""
    size = start
    while size >= minimum:
        f = font(kind, size)
        lines = wrap(draw, text, f, max_w)
        h = len(lines) * size * spacing
        if h <= max_h:
            return f, lines, size
        size -= 2
    f = font(kind, minimum)
    return f, wrap(draw, text, f, max_w), minimum


def draw_lines(draw, xy, lines, f, size, fill, spacing=1.2):
    x, y = xy
    for line in lines:
        draw.text((x, y), line, font=f, fill=fill)
        y += size * spacing
    return y


def base(colors):
    img = Image.new("RGB", (W, H), hex_to_rgb(colors["background"]))
    return img, ImageDraw.Draw(img)


def footer(draw, colors, handle, idx, total):
    f = font("semibold", 30)
    draw.text((PAD, H - PAD - 10), handle, font=f, fill=hex_to_rgb(colors["muted"]))
    label = f"{idx}/{total}"
    tw = draw.textlength(label, font=f)
    draw.text((W - PAD - tw, H - PAD - 10), label, font=f, fill=hex_to_rgb(colors["muted"]))


def render_cover(slide, colors, handle, pillar_name, total):
    img, d = base(colors)
    accent = hex_to_rgb(colors["accent"])
    # Säulen-Label
    f_lbl = font("semibold", 32)
    lbl = pillar_name.upper()
    lw = d.textlength(lbl, font=f_lbl)
    d.rounded_rectangle((PAD, PAD + 40, PAD + lw + 48, PAD + 40 + 64), radius=32, outline=accent, width=3)
    d.text((PAD + 24, PAD + 52), lbl, font=f_lbl, fill=accent)
    # Hook
    top = PAD + 200
    f, lines, size = fit(d, slide["headline"], "bold", W - 2 * PAD, 620, 104, 60, 1.12)
    y = draw_lines(d, (PAD, top), lines, f, size, hex_to_rgb(colors["text"]), 1.12)
    d.rectangle((PAD, y + 40, PAD + 140, y + 52), fill=accent)
    if slide.get("body"):
        fb, lb, sb = fit(d, slide["body"], "regular", W - 2 * PAD, H - (y + 110) - PAD - 140, 44, 30, 1.35)
        draw_lines(d, (PAD, y + 100), lb, fb, sb, hex_to_rgb(colors["muted"]), 1.35)
    # Wisch-Hinweis
    f_sw = font("semibold", 34)
    sw = "Wischen →"
    d.text((W - PAD - d.textlength(sw, font=f_sw), H - PAD - 120), sw, font=f_sw, fill=accent)
    footer(d, colors, handle, 1, total)
    return img


def render_content(slide, colors, handle, idx, total):
    img, d = base(colors)
    accent = hex_to_rgb(colors["accent"])
    text_c = hex_to_rgb(colors["text"])
    # Nummer
    d.text((PAD, PAD + 20), f"{idx - 1:02d}", font=font("bold", 72), fill=accent)
    top = PAD + 170
    avail_bottom = H - PAD - 120

    # 1) Layout berechnen
    f, lines, size = fit(d, slide["headline"], "bold", W - 2 * PAD, 330, 80, 44, 1.15)
    head_h = len(lines) * size * 1.15
    box = (slide.get("box") or "").strip()
    body = (slide.get("body") or "").strip()
    y_after_head = top + head_h + 44
    box_h_budget = min(600, avail_bottom - y_after_head - (200 if body else 0)) if box else 0
    body_h = 0
    if body:
        body_budget = avail_bottom - y_after_head - (box_h_budget + 40 if box else 0)
        fb, lb, sb = fit(d, body, "regular", W - 2 * PAD, body_budget, 52, 28, 1.4)
        body_h = len(lb) * sb * 1.4 + 30
    box_h = 0
    if box:
        fm, lm, sm = fit(d, box, "mono", W - 2 * PAD - 88, box_h_budget - 64, 36, 20, 1.35)
        box_h = len(lm) * sm * 1.35 + 64
    total_h = head_h + 44 + body_h + box_h
    # 2) Block optisch mittig setzen (aber nie über die Nummer)
    y = max(top, top + (avail_bottom - top - total_h) * 0.4)

    y = draw_lines(d, (PAD, y), lines, f, size, text_c, 1.15) + 44
    if body:
        y = draw_lines(d, (PAD, y), lb, fb, sb, hex_to_rgb(colors["muted"]), 1.4) + 30
    if box:
        d.rounded_rectangle((PAD, y, W - PAD, y + box_h), radius=24, fill=hex_to_rgb(colors["surface"]))
        d.rectangle((PAD, y + 24, PAD + 8, y + box_h - 24), fill=accent)
        draw_lines(d, (PAD + 40, y + 32), lm, fm, sm, text_c, 1.35)
    footer(d, colors, handle, idx, total)
    return img


def render_cta(cta, colors, handle, total):
    img, d = base(colors)
    accent = hex_to_rgb(colors["accent"])
    f, lines, size = fit(d, cta["headline"], "bold", W - 2 * PAD, 520, 88, 56, 1.15)
    block_h = len(lines) * size * 1.15
    y = (H - block_h) / 2 - 140
    y = draw_lines(d, (PAD, y), lines, f, size, hex_to_rgb(colors["text"]), 1.15) + 40
    fb, lb, sb = fit(d, cta["body"], "regular", W - 2 * PAD, 260, 44, 30, 1.4)
    y = draw_lines(d, (PAD, y), lb, fb, sb, hex_to_rgb(colors["muted"]), 1.4) + 60
    fh = font("bold", 52)
    d.text((PAD, y), handle, font=fh, fill=accent)
    if cta.get("footer"):
        ff = font("semibold", 34)
        txt = f"↓  {cta['footer']}"
        d.text((PAD, H - PAD - 120), txt, font=ff, fill=accent)
    footer(d, colors, handle, total, total)
    return img


def render_post(post_dir: Path, cfg: dict) -> list[Path]:
    post = json.loads((post_dir / "post.json").read_text(encoding="utf-8"))
    colors = cfg["brand"]["colors"]
    handle = cfg["brand"]["handle"]
    pillars = {p["id"]: p["name"] for p in cfg["content"]["pillars"]}
    slides = post["slides"]
    total = len(slides) + 1  # + Abschluss-Slide
    for old in post_dir.glob("slide-*.jpg"):
        old.unlink()
    out = []
    for i, s in enumerate(slides, start=1):
        if i == 1:
            img = render_cover(s, colors, handle, pillars.get(post.get("pillar"), ""), total)
        else:
            img = render_content(s, colors, handle, i, total)
        p = post_dir / f"slide-{i:02d}.jpg"
        img.save(p, "JPEG", quality=92, optimize=True)
        out.append(p)
    p = post_dir / f"slide-{total:02d}.jpg"
    render_cta(cfg["content"]["cta_slide"], colors, handle, total).save(p, "JPEG", quality=92, optimize=True)
    out.append(p)
    post["images"] = [x.name for x in out]
    (post_dir / "post.json").write_text(json.dumps(post, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return out


if __name__ == "__main__":
    from .common import load_config

    ap = argparse.ArgumentParser(description="Slides für einen Post-Ordner neu rendern")
    ap.add_argument("post_dir", type=Path)
    args = ap.parse_args()
    for p in render_post(args.post_dir, load_config()):
        print(p)
