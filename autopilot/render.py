"""Rendert ein Karussell (post.json) zu JPEG-Slides im Format 1080x1350 (4:5).

Markenformat „Editor-Fenster“: Jede Slide ist ein Fenster, in dem Kollege KI gerade tippt.
  - Titelleiste „kollege.ki — <säule>.md“, Statuszeile „● KI tippt …“ und Seitenzahl
  - Rahmenfarbe je Säule (config.yaml → brand.frames), damit der Feed einen Rhythmus bekommt
  - Schrift: Bricolage Grotesque (Text), Geist Mono (Fenster und Code-Boxen) – beide OFL, liegen in assets/fonts
  - *Sternchen* im Text markieren Schlüsselwörter in der Akzentfarbe
  - der Cursor aus dem Logo steht hinter der Cover-Headline und im Abschluss-Slide
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

W, H = 1080, 1350
M = 44            # Abstand Fenster zum Bildrand
X = 130           # linker Textrand im Fenster
INNER = W - 2 * X
TITLE_H = 84
STATUS_H = 74

ASSETS = Path(__file__).resolve().parent.parent / "assets" / "fonts"
FONT_FILES = {
    "head": ["BricolageGrotesque-Bold.ttf", "Inter-Bold.otf", "DejaVuSans-Bold.ttf"],
    "body": ["BricolageGrotesque-Regular.ttf", "Inter-Regular.otf", "DejaVuSans.ttf"],
    "mono": ["GeistMono-Regular.ttf", "DejaVuSansMono.ttf"],
    "mono_bold": ["GeistMono-Bold.ttf", "DejaVuSansMono-Bold.ttf"],
}
FONT_DIRS = [ASSETS, Path("/usr/share/fonts/opentype/inter"), Path("/usr/share/fonts/truetype/dejavu")]
_font_cache: dict = {}

# Schriftgrößen (Start, Minimum) – verkleinert wird nur, wenn der Text sonst nicht passt
SIZES = {"cover": (100, 72), "head": (66, 50), "body": (42, 32), "box": (34, 26)}

DEFAULT_FRAMES = {"tool": "light", "prompt": "accent", "skill": "dark", "workflow": "light", "making_of": "dark"}
LIGHT = "#E8E9E4"


def font(kind: str, size: int) -> ImageFont.FreeTypeFont:
    key = (kind, size)
    if key not in _font_cache:
        for name in FONT_FILES[kind]:
            for d in FONT_DIRS:
                if (d / name).exists():
                    _font_cache[key] = ImageFont.truetype(str(d / name), size)
                    break
            if key in _font_cache:
                break
        else:
            raise SystemExit("Keine Schrift gefunden – assets/fonts fehlt im Repo.")
    return _font_cache[key]


def rgb(h: str) -> tuple[int, int, int]:
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def shade(c: tuple, delta: int) -> tuple:
    return tuple(max(0, min(255, v + delta)) for v in c)


# ---------------------------------------------------------------- Text mit *Hervorhebungen*

def tokens(text: str) -> list[list[tuple[str, bool]]]:
    paras = []
    for para in text.split("\n"):
        words, accent = [], False
        for part in re.split(r"(\*)", para):
            if part == "*":
                accent = not accent
                continue
            words += [(w, accent) for w in part.split()]
        paras.append(words)
    return paras


def wrap(draw, text: str, f, max_w: float):
    space = draw.textlength(" ", font=f)
    lines = []
    for words in tokens(text):
        if not words:
            lines.append([])
            continue
        cur, cur_w = [], 0.0
        for w, acc in words:
            ww = draw.textlength(w, font=f)
            if cur and cur_w + space + ww > max_w:
                lines.append(cur)
                cur, cur_w = [], 0.0
            cur_w += (space if cur else 0) + ww
            cur.append((w, acc))
        lines.append(cur)
    return lines


def fit(draw, text, kind, max_w, max_h, sizes, spacing):
    size, minimum = sizes
    while size >= minimum:
        f = font(kind, size)
        lines = wrap(draw, text, f, max_w)
        if len(lines) * size * spacing <= max_h:
            return f, lines, size
        size -= 2
    f = font(kind, minimum)
    return f, wrap(draw, text, f, max_w), minimum


def draw_lines(draw, x, y, lines, f, size, fill, accent, spacing):
    space = draw.textlength(" ", font=f)
    end = (x, y)
    for line in lines:
        cx = x
        for w, acc in line:
            draw.text((cx, y), w, font=f, fill=accent if acc else fill)
            cx += draw.textlength(w, font=f) + space
        end = (cx - space, y)
        y += size * spacing
    return y, end


# ---------------------------------------------------------------- Fenster

class Theme:
    def __init__(self, cfg: dict, pillar: str):
        c = cfg["brand"]["colors"]
        self.bg = rgb(c["background"])
        self.win = shade(self.bg, 7)
        self.edge = shade(self.bg, 25)
        self.surface = rgb(c["surface"])
        self.text = rgb(c["text"])
        self.muted = rgb(c["muted"])
        self.accent = rgb(c["accent"])
        frames = {**DEFAULT_FRAMES, **cfg["brand"].get("frames", {})}
        kind = frames.get(pillar, "dark")
        self.outer = {"accent": self.accent, "light": rgb(c.get("light", LIGHT))}.get(kind, self.bg)


def window(theme: Theme, title: str, status: str, page: str):
    img = Image.new("RGB", (W, H), theme.outer)
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((M, M, W - M, H - M), radius=34, fill=theme.win, outline=theme.edge, width=2)
    for i in range(3):
        x = M + 34 + i * 38
        d.ellipse((x, M + 32, x + 20, M + 52), fill=shade(theme.win, 45))
    tf = font("mono", 26)
    d.text(((W - d.textlength(title, font=tf)) / 2, M + 27), title, font=tf, fill=theme.muted)
    d.line((M, M + TITLE_H, W - M, M + TITLE_H), fill=theme.edge, width=2)
    d.line((M, H - M - STATUS_H, W - M, H - M - STATUS_H), fill=theme.edge, width=2)
    sf = font("mono", 24)
    d.ellipse((M + 34, H - M - 46, M + 46, H - M - 34), fill=theme.accent)
    d.text((M + 60, H - M - 53), status, font=sf, fill=theme.accent)
    d.text((W - M - 34 - d.textlength(page, font=sf), H - M - 53), page, font=sf, fill=theme.muted)
    return img, d


def cursor(d, theme, x, y, size):
    w = max(10, int(size * 0.12))
    d.rounded_rectangle((x + size * 0.16, y + size * 0.16, x + size * 0.16 + w, y + size * 1.0),
                        radius=w // 3, fill=theme.accent)


def file_title(handle: str, pillar: str) -> str:
    name = {"making_of": "logbuch", "tool": "tool-check"}.get(pillar, pillar or "notiz")
    return f"{handle.lstrip('@')} — {name}.md"


TOP = M + TITLE_H + 80
BOTTOM = H - M - STATUS_H - 70


# ---------------------------------------------------------------- Slides

def render_cover(slide, theme, title, label, total):
    img, d = window(theme, title, "KI tippt …", f"1 / {total}")
    d.text((X, TOP), f"# {label.upper()}", font=font("mono_bold", 26), fill=theme.accent)
    f, lines, size = fit(d, slide["headline"], "head", INNER - 60, 560, SIZES["cover"], 1.08)
    head_h = len(lines) * size * 1.08
    body = (slide.get("body") or "").strip()
    body_h = 0
    if body:
        fb, lb, sb = fit(d, body, "body", INNER, 180, SIZES["body"], 1.35)
        body_h = len(lb) * sb * 1.35 + 50
    top = TOP + 100
    y = top + max(0, (BOTTOM - top - head_h - body_h) * 0.3)
    y, (ex, ey) = draw_lines(d, X, y, lines, f, size, theme.text, theme.accent, 1.08)
    cursor(d, theme, ex, ey, size)
    if body:
        draw_lines(d, X, y + 50 - size * 0.08, lb, fb, sb, theme.muted, theme.accent, 1.35)
    return img


def render_content(slide, theme, title, idx, total):
    img, d = window(theme, title, "KI tippt …", f"{idx} / {total}")
    f, lines, size = fit(d, slide["headline"], "head", INNER, 300, SIZES["head"], 1.1)
    head_h = len(lines) * size * 1.1
    box = (slide.get("box") or "").strip()
    body = (slide.get("body") or "").strip()
    avail = BOTTOM - TOP - head_h - 40
    box_budget = min(620, avail - (170 if body else 0) - 40) if box else 0
    body_h = 0
    if body:
        fb, lb, sb = fit(d, body, "body", INNER, avail - (box_budget + 80 if box else 0), SIZES["body"], 1.4)
        body_h = len(lb) * sb * 1.4
    box_h = 0
    if box:
        fm, lm, sm = fit(d, box, "mono", INNER - 100, box_budget - 70, SIZES["box"], 1.45)
        box_h = len(lm) * sm * 1.45 + 70
    total_h = head_h + 40 + body_h + (80 + box_h if box else 0)
    y = TOP + max(0, (BOTTOM - TOP - total_h) * 0.35)

    y, _ = draw_lines(d, X, y, lines, f, size, theme.text, theme.accent, 1.1)
    y += 40 - size * 0.1
    if body:
        y, _ = draw_lines(d, X, y, lb, fb, sb, theme.muted, theme.accent, 1.4)
        y -= sb * 0.4
    if box:
        y += 80
        lf = font("mono", 24)
        d.text((W - X - d.textlength("kopieren", font=lf), y - 38), "kopieren", font=lf, fill=theme.muted)
        d.rounded_rectangle((X, y, W - X, y + box_h), radius=22, fill=theme.surface)
        d.text((X + 28, y + 35), ">", font=fm, fill=theme.accent)
        draw_lines(d, X + 70, y + 35, lm, fm, sm, theme.text, theme.accent, 1.45)
    return img


def render_cta(cta, theme, title, handle, total):
    img, d = window(theme, title, "gespeichert", f"{total} / {total}")
    f, lines, size = fit(d, cta["headline"], "head", INNER - 60, 480, (84, 60), 1.08)
    fb, lb, sb = fit(d, cta["body"], "body", INNER, 220, SIZES["body"], 1.4)
    block = len(lines) * size * 1.08 + 44 + len(lb) * sb * 1.4 + 120
    y = TOP + max(0, (BOTTOM - TOP - block) * 0.4)
    y, (ex, ey) = draw_lines(d, X, y, lines, f, size, theme.text, theme.accent, 1.08)
    cursor(d, theme, ex, ey, size)
    y, _ = draw_lines(d, X, y + 44 - size * 0.08, lb, fb, sb, theme.muted, theme.accent, 1.4)
    d.text((X, y + 40), handle, font=font("head", 54), fill=theme.accent)
    if cta.get("footer"):
        ff = font("mono", 26)
        d.text((X, BOTTOM - 10), f"↓ {cta['footer']}", font=ff, fill=theme.muted)
    return img


def render_post(post_dir: Path, cfg: dict) -> list[Path]:
    post = json.loads((post_dir / "post.json").read_text(encoding="utf-8"))
    handle = cfg["brand"]["handle"]
    pillar = post.get("pillar", "")
    pillars = {p["id"]: p["name"] for p in cfg["content"]["pillars"]}
    theme = Theme(cfg, pillar)
    title = file_title(handle, pillar)
    slides = post["slides"]
    total = len(slides) + 1  # + Abschluss-Slide
    for old in post_dir.glob("slide-*.jpg"):
        old.unlink()
    out = []
    for i, s in enumerate(slides, start=1):
        img = (render_cover(s, theme, title, pillars.get(pillar, pillar), total) if i == 1
               else render_content(s, theme, title, i, total))
        p = post_dir / f"slide-{i:02d}.jpg"
        img.save(p, "JPEG", quality=92, optimize=True)
        out.append(p)
    p = post_dir / f"slide-{total:02d}.jpg"
    render_cta(cfg["content"]["cta_slide"], theme, title, handle, total).save(p, "JPEG", quality=92, optimize=True)
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
