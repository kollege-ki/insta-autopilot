"""Macht aus einem Karussell ein Reel (1080x1920, H.264, höchstens reels.max_seconds, Standard 35 s).

Instagram lehnt per API hochgeladene Reels über ca. 40 Sekunden derzeit mit
„ProcessingFailedError“ ab – darum werden lange Posts schneller durchgeblättert.

Ablauf im Video:
  1. Cover: die Headline wird Zeichen für Zeichen getippt, danach blinkt der Cursor
  2. Inhalts-Slides: je nach Textmenge 2,5–6 Sekunden
  3. Abschluss-Slide mit blinkendem Cursor

Ton: Liegen MP3-Dateien in assets/music (z. B. lizenzfreie Musik), wird zufällig eine gewählt
und am Ende ausgeblendet. Sonst eine stille Tonspur – Instagram erwartet eine.
Braucht ffmpeg (im Workflow per apt installiert). Fehlt es, wird das Reel übersprungen.
"""
from __future__ import annotations

import random
import shutil
import subprocess
from pathlib import Path

from PIL import Image

from .render import (Theme, file_title, render_content, render_cover, render_cta, tokens)

FPS = 30
VW, VH = 1080, 1920
SLIDE_W = 1000                      # Slide etwas kleiner, damit Instagrams Bedienelemente unten nichts verdecken
SLIDE_H = int(SLIDE_W * 1350 / 1080)
SLIDE_Y = 230
ROOT = Path(__file__).resolve().parent.parent


def words(slide: dict) -> int:
    text = " ".join(str(slide.get(k, "")) for k in ("headline", "body", "box")).replace("*", "")
    return len(text.split())


def compose(slide_img, outer) -> bytes | None:
    if slide_img is None:
        return None
    canvas = Image.new("RGB", (VW, VH), outer)
    canvas.paste(slide_img.resize((SLIDE_W, SLIDE_H), Image.LANCZOS), ((VW - SLIDE_W) // 2, SLIDE_Y))
    return canvas.tobytes()


def build_frames(post: dict, cfg: dict, render: bool = True):
    """Liefert (Frame-Bytes, Anzahl Wiederholungen) in Reihenfolge.
    render=False liefert nur die Wiederholungen (zum Vorausberechnen der Dauer)."""
    handle = cfg["brand"]["handle"]
    pillar = post.get("pillar", "")
    pillars = {p["id"]: p["name"] for p in cfg["content"]["pillars"]}
    theme = Theme(cfg, pillar)
    title = file_title(handle, pillar)
    slides = post["slides"]
    total = len(slides) + 1
    label = pillars.get(pillar, pillar)
    blink = FPS // 2

    def rc(*a, **k):
        return render_cover(*a, **k) if render else None

    def rn(*a, **k):
        return render_content(*a, **k) if render else None

    def rt(*a, **k):
        return render_cta(*a, **k) if render else None

    # 1) Tippen
    cover = slides[0]
    n_chars = sum(len(t) for para in tokens(cover["headline"]) for word in para for t, _ in word)
    step = max(1, -(-n_chars // int(FPS * 1.6)))  # höchstens ca. 1,6 s Tippen
    for n in range(0, n_chars + step, step):
        yield compose(rc(cover, theme, title, label, total, reveal=min(n, n_chars)), theme.outer), 1
    # 2) Cover komplett, Cursor blinkt
    on = compose(rc(cover, theme, title, label, total), theme.outer)
    off = compose(rc(cover, theme, title, label, total, cursor_on=False), theme.outer)
    for i in range(4):
        yield (on if i % 2 == 0 else off), blink
    # 3) Inhalts-Slides – Lesezeit nach Textmenge, bei Bedarf gestaucht auf max_seconds
    secs = [min(6.0, max(2.5, 1.2 + words(s) / 4.0)) for s in slides[1:]]
    n_typing = len(range(0, n_chars + step, step))
    fixed = n_typing / FPS + (4 + 6) * blink / FPS
    budget = float(cfg.get("reels", {}).get("max_seconds", 35)) - fixed
    if secs and sum(secs) > budget:
        factor = max(budget, 0) / sum(secs)
        secs = [max(1.8, x * factor) for x in secs]
    for (i, s), sec in zip(enumerate(slides[1:], start=2), secs):
        yield compose(rn(s, theme, title, i, total), theme.outer), int(sec * FPS)
    # 4) Abschluss, Cursor blinkt
    cta = cfg["content"]["cta_slide"]
    on = compose(rt(cta, theme, title, handle, total), theme.outer)
    off = compose(rt(cta, theme, title, handle, total, cursor_on=False), theme.outer)
    for i in range(6):
        yield (on if i % 2 == 0 else off), blink


def pick_music(cfg: dict) -> Path | None:
    folder = ROOT / cfg.get("reels", {}).get("music_dir", "assets/music")
    tracks = sorted(folder.glob("*.mp3")) if folder.exists() else []
    return random.choice(tracks) if tracks else None


def build_reel(post_dir: Path, post: dict, cfg: dict) -> dict | None:
    if not shutil.which("ffmpeg"):
        print("WARNUNG: ffmpeg fehlt – Reel übersprungen.", flush=True)
        return None
    out = post_dir / "reel.mp4"
    plan = [r for _, r in build_frames(post, cfg, render=False)]
    duration = sum(plan) / FPS
    first_still = next(i for i, r in enumerate(plan) if r > 1)   # erstes Standbild = fertig getipptes Cover
    thumb_ms = int(sum(plan[:first_still]) / FPS * 1000) + 100
    music = pick_music(cfg)
    if music:
        audio = ["-i", str(music)]
        afilter = ["-af", f"apad,afade=t=out:st={max(0, duration - 1.5):.2f}:d=1.5,volume=0.7"]
    else:
        audio = ["-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo"]
        afilter = []
    cmd = ["ffmpeg", "-y", "-loglevel", "error",
           "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{VW}x{VH}", "-r", str(FPS), "-i", "-",
           *audio, "-map", "0:v", "-map", "1:a", "-t", f"{duration:.2f}", *afilter,
           "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p",
           "-profile:v", "high", "-level", "4.1", "-g", str(2 * FPS), "-r", str(FPS),
           "-c:a", "aac", "-b:a", "128k", "-ar", "48000",
           "-movflags", "+faststart", str(out)]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    try:
        for data, repeat in build_frames(post, cfg):
            for _ in range(repeat):
                proc.stdin.write(data)
    except BrokenPipeError:
        pass
    finally:
        try:
            proc.stdin.close()
        except BrokenPipeError:
            pass
    if proc.wait() != 0 or not out.exists():
        print("WARNUNG: Reel konnte nicht erzeugt werden.", flush=True)
        return None
    return {"file": out.name, "seconds": round(duration, 1), "thumb_offset_ms": thumb_ms,
            "music": music.name if music else None}
