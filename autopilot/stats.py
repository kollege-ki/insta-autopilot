"""Tracking für Build in Public und die spätere Verkaufsvorlage.

Läuft täglich nach den Insights und schreibt:
  data/account_daily.csv – Follower und Beitragszahl pro Tag
  data/milestones.json   – jede Änderung am Setup (automatisch aus config.yaml + „Meilenstein:“ im Journal)
  data/impact.md         – Vorher/Nachher je Meilenstein: Reichweite, Score, Follower-Zuwachs
  docs/index.html        – über cockpit.py (Projektcockpit)
"""
from __future__ import annotations

import csv
import hashlib
import html
import json
import re
from datetime import date, datetime, timedelta
from statistics import mean

from .common import (CONTENT, DATA, INSIGHTS_CSV, ROOT, STATE_FILE, load_config, load_json,
                     now, save_json)

DAILY_CSV = DATA / "account_daily.csv"
MILESTONES = DATA / "milestones.json"
IMPACT = DATA / "impact.md"
WINDOW = 14  # Tage vor/nach einem Meilenstein


# ---------------------------------------------------------------- Daten sammeln

def snapshot(cfg: dict) -> None:
    from .instagram import Instagram

    me = Instagram(cfg).get("me", fields="followers_count,media_count")
    today = now(cfg).date().isoformat()
    rows = []
    if DAILY_CSV.exists():
        with open(DAILY_CSV, encoding="utf-8") as f:
            rows = [r for r in csv.DictReader(f) if r["date"] != today]
    rows.append({"date": today, "followers": me.get("followers_count", 0), "media": me.get("media_count", 0)})
    with open(DAILY_CSV, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["date", "followers", "media"])
        w.writeheader()
        w.writerows(rows)


def tracked_settings(cfg: dict) -> dict:
    """Die Einstellungen, deren Änderung als Meilenstein zählt."""
    c, p = cfg["content"], cfg["posting"]
    return {
        "Modell": cfg["model"],
        "Posts pro Tag": p["posts_per_day"],
        "Uhrzeiten": ", ".join(p["slots"]),
        "Slot-Modus": p["mode"],
        "Ideen pro Post": c.get("ideas_per_post", 1),
        "Slides": f"{c['slides_min']}–{c['slides_max']}",
        "Säulen": ", ".join(f"{x['id']}×{x['weight']}" for x in c["pillars"]),
        "Formate": len(c.get("formats", [])),
        "Verbotene Floskeln": len(c.get("banned_phrases", [])),
        "Gewichte lernen": c.get("adapt_weights", False),
        "Design": "/".join(cfg["brand"]["colors"].values()),
    }


def update_milestones(cfg: dict) -> list[dict]:
    ms = load_json(MILESTONES, [])
    state = load_json(STATE_FILE, {})
    today = now(cfg).date().isoformat()

    # 1) automatisch: Änderungen an config.yaml
    current = tracked_settings(cfg)
    before = state.get("tracked_settings")
    if before is None:
        ms.append({"date": today, "source": "auto", "title": "Tracking gestartet",
                   "details": "; ".join(f"{k}: {v}" for k, v in current.items())})
    else:
        changes = [f"{k}: {before.get(k)} → {v}" for k, v in current.items() if before.get(k) != v]
        if changes:
            ms.append({"date": today, "source": "auto", "title": "Einstellung geändert", "details": "; ".join(changes)})
    state["tracked_settings"] = current
    save_json(STATE_FILE, state)

    # 2) manuell: Zeilen „- Meilenstein: …“ unter „## TT.MM.JJJJ“ im Journal
    journal = (CONTENT / "journal.md").read_text(encoding="utf-8") if (CONTENT / "journal.md").exists() else ""
    current_date = None
    known = {(m["date"], m["title"]) for m in ms}
    for line in journal.splitlines():
        h = re.match(r"^##\s*(\d{2})\.(\d{2})\.(\d{4})", line)
        if h:
            current_date = f"{h.group(3)}-{h.group(2)}-{h.group(1)}"
            continue
        m = re.match(r"^\s*[-*]\s*Meilenstein:\s*(.+)$", line, re.I)
        if m and current_date and (current_date, m.group(1).strip()) not in known:
            ms.append({"date": current_date, "source": "journal", "title": m.group(1).strip(), "details": ""})
            known.add((current_date, m.group(1).strip()))

    ms.sort(key=lambda m: m["date"])
    save_json(MILESTONES, ms)
    return ms


def load_posts() -> list[dict]:
    if not INSIGHTS_CSV.exists():
        return []
    with open(INSIGHTS_CSV, encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    for r in rows:
        r["d"] = datetime.fromisoformat(r["posted_at"]).date()
        for k in ("reach", "saved", "shares", "likes", "comments", "score"):
            r[k] = int(float(r.get(k) or 0))
    return sorted(rows, key=lambda r: r["d"])


def load_daily() -> list[dict]:
    if not DAILY_CSV.exists():
        return []
    with open(DAILY_CSV, encoding="utf-8") as f:
        return [{"d": date.fromisoformat(r["date"]), "followers": int(r["followers"]), "media": int(r["media"])}
                for r in csv.DictReader(f)]


# ---------------------------------------------------------------- Auswertung

def follower_rate(daily, start, end):
    pts = [r for r in daily if start <= r["d"] < end]
    if len(pts) < 2:
        return None
    days = (pts[-1]["d"] - pts[0]["d"]).days or 1
    return (pts[-1]["followers"] - pts[0]["followers"]) / days


def pct(a, b):
    if a is None or b is None or a == 0:
        return "–"
    return f"{(b - a) / abs(a) * 100:+.0f} %"


def impact(ms, posts, daily) -> list[dict]:
    out = []
    for m in ms:
        d = date.fromisoformat(m["date"])
        pre = [p for p in posts if d - timedelta(days=WINDOW) <= p["d"] < d]
        post = [p for p in posts if d <= p["d"] < d + timedelta(days=WINDOW)]
        res = {**m, "n_pre": len(pre), "n_post": len(post)}
        if len(pre) >= 3 and len(post) >= 3:
            res.update(reach_pre=mean(p["reach"] for p in pre), reach_post=mean(p["reach"] for p in post),
                       score_pre=mean(p["score"] for p in pre), score_post=mean(p["score"] for p in post))
        res["fol_pre"] = follower_rate(daily, d - timedelta(days=WINDOW), d)
        res["fol_post"] = follower_rate(daily, d, d + timedelta(days=WINDOW))
        out.append(res)
    return out


def fol_txt(r: dict) -> str:
    if r["fol_pre"] is None or r["fol_post"] is None:
        return "–"
    return f"{r['fol_pre']:.1f} → {r['fol_post']:.1f}".replace(".", ",")


def fmt_date(iso: str) -> str:
    y, m, d = iso.split("-")
    return f"{d}.{m}.{y}"


def write_impact(rows, cfg) -> None:
    lines = [f"# Wirkung der Meilensteine (Stand {now(cfg):%d.%m.%Y})", "",
             f"Vergleich jeweils {WINDOW} Tage vorher vs. {WINDOW} Tage nachher. "
             "Zeigt Zusammenhänge, keinen Beweis – es ändern sich immer mehrere Dinge gleichzeitig.", "",
             "| Datum | Meilenstein | Ø Reichweite/Post | Ø Score/Post | Follower/Tag | Posts vorher/nachher |",
             "|---|---|---|---|---|---|"]
    for r in rows:
        reach = (f"{r['reach_pre']:.0f} → {r['reach_post']:.0f} ({pct(r['reach_pre'], r['reach_post'])})"
                 if "reach_pre" in r else "zu wenig Daten")
        score = (f"{r['score_pre']:.0f} → {r['score_post']:.0f} ({pct(r['score_pre'], r['score_post'])})"
                 if "score_pre" in r else "–")
        fol = fol_txt(r)
        title = r["title"] + (f" ({r['details']})" if r["source"] == "auto" and r["title"] != "Tracking gestartet" else "")
        lines.append(f"| {fmt_date(r['date'])} | {title} | {reach} | {score} | {fol} | {r['n_pre']}/{r['n_post']} |")
    IMPACT.write_text("\n".join(lines) + "\n", encoding="utf-8")


def stats_summary(cfg) -> str:
    """Kurzfassung echter Zahlen für den Generator (Making-of-Posts)."""
    daily, posts = load_daily(), load_posts()
    parts = []
    if daily:
        first, last = daily[0], daily[-1]
        parts.append(f"Follower aktuell: {last['followers']} (am {first['d']:%d.%m.%Y}: {first['followers']}).")
    if posts:
        parts.append(f"Ausgewertete Posts: {len(posts)}, Ø Reichweite {mean(p['reach'] for p in posts):.0f}, "
                     f"bester Post: „{max(posts, key=lambda p: p['score'])['title']}“.")
    if IMPACT.exists():
        parts.append(IMPACT.read_text(encoding="utf-8")[-2500:])
    return "\n".join(parts) or "Noch keine Zahlen."


# ---------------------------------------------------------------- Dashboard

def svg_line(daily, ms, colors, w=900, h=260):
    if len(daily) < 2:
        return "<p class='muted'>Noch zu wenig Tage für die Kurve.</p>"
    x0, x1 = daily[0]["d"], daily[-1]["d"]
    span = max((x1 - x0).days, 1)
    vmax = max(r["followers"] for r in daily) or 1
    vmin = min(r["followers"] for r in daily)
    rng = max(vmax - vmin, 1)
    X = lambda d: 40 + (d - x0).days / span * (w - 60)
    Y = lambda v: h - 30 - (v - vmin) / rng * (h - 60)
    pts = " ".join(f"{X(r['d']):.1f},{Y(r['followers']):.1f}" for r in daily)
    marks = ""
    for m in ms:
        d = date.fromisoformat(m["date"])
        if x0 <= d <= x1:
            marks += (f"<line x1='{X(d):.1f}' x2='{X(d):.1f}' y1='20' y2='{h - 30}' stroke='{colors['muted']}' "
                      f"stroke-dasharray='4 4'><title>{html.escape(m['title'])}</title></line>")
    return (f"<svg viewBox='0 0 {w} {h}' role='img' aria-label='Follower-Verlauf'>{marks}"
            f"<polyline points='{pts}' fill='none' stroke='{colors['accent']}' stroke-width='3'/>"
            f"<text x='40' y='{h - 8}' fill='{colors['muted']}' font-size='13'>{x0:%d.%m.}</text>"
            f"<text x='{w - 20}' y='{h - 8}' fill='{colors['muted']}' font-size='13' text-anchor='end'>{x1:%d.%m.}</text>"
            f"<text x='{w - 20}' y='{Y(daily[-1]['followers']) - 8:.1f}' fill='{colors['text']}' font-size='14' "
            f"text-anchor='end'>{daily[-1]['followers']}</text></svg>")


def svg_bars(posts, colors, w=900, h=220):
    posts = posts[-40:]
    if not posts:
        return "<p class='muted'>Noch keine ausgewerteten Posts.</p>"
    vmax = max(p["reach"] for p in posts) or 1
    bw = (w - 40) / len(posts)
    bars = "".join(
        f"<rect x='{20 + i * bw:.1f}' y='{h - 20 - p['reach'] / vmax * (h - 40):.1f}' width='{bw * 0.7:.1f}' "
        f"height='{p['reach'] / vmax * (h - 40):.1f}' fill='{colors['accent']}' rx='2'>"
        f"<title>{p['d']:%d.%m.} · {html.escape(p['title'])} · Reichweite {p['reach']}</title></rect>"
        for i, p in enumerate(posts))
    return f"<svg viewBox='0 0 {w} {h}' role='img' aria-label='Reichweite pro Post'>{bars}</svg>"


def main() -> None:
    cfg = load_config()
    try:
        snapshot(cfg)
    except SystemExit:
        raise
    except Exception as e:  # noqa: BLE001 – Statistik soll nie den Rest blockieren
        print(f"Follower-Stand nicht abrufbar: {e}")
    ms = update_milestones(cfg)
    posts, daily = load_posts(), load_daily()
    rows = impact(ms, posts, daily)
    write_impact(rows, cfg)
    from .cockpit import build
    build()
    print(IMPACT.read_text(encoding="utf-8"))


if __name__ == "__main__":
    main()
