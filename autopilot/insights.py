"""Holt Instagram-Insights für gepostete Beiträge, wertet Uhrzeiten, Säulen und
Formate aus und schreibt:
  data/insights.csv  – Rohdaten pro Post
  data/learnings.md  – Zusammenfassung, die der Generator mitliest
  data/state.json    – beste Uhrzeiten + Gewichtungsfaktoren für Säulen
"""
from __future__ import annotations

import csv
from collections import defaultdict
from datetime import datetime, timedelta
from statistics import mean

from .common import (HISTORY_FILE, INSIGHTS_CSV, LEARNINGS_FILE, STATE_FILE, load_config,
                     load_json, now, save_json)

METRICS = ["reach", "saved", "shares", "likes", "comments", "total_interactions", "views"]
FIELDS = ["type", "folder", "title", "pillar", "format", "slot", "weekday", "posted_at", "media_id"] + METRICS + ["score"]
WEEKDAYS = ["Mo", "Di", "Mi", "Do", "Fr", "Sa", "So"]


def score(row: dict) -> float:
    """Gewichtet, was der Algorithmus für Reichweite bei Nicht-Followern stark wertet:
    Teilen und Speichern vor Likes."""
    return row.get("shares", 0) * 4 + row.get("saved", 0) * 3 + row.get("comments", 0) * 2 + row.get("likes", 0)


def fetch(cfg: dict) -> list[dict]:
    from .instagram import Instagram

    ig = Instagram(cfg)
    rows = []
    cutoff = now(cfg) - timedelta(hours=24)
    frozen = now(cfg) - timedelta(days=60)
    old = {}
    if INSIGHTS_CSV.exists():
        with open(INSIGHTS_CSV, encoding="utf-8") as f:
            old = {r["media_id"]: r for r in csv.DictReader(f)}
    for h in load_json(HISTORY_FILE, []):
        posted = datetime.fromisoformat(h["posted_at"])
        if posted > cutoff:
            continue  # erst nach 24 h aussagekräftig
        targets = [("karussell", h["media_id"])]
        if h.get("reel_media_id"):
            targets.append(("reel", h["reel_media_id"]))
        for kind, mid in targets:
            if posted < frozen and mid in old:
                # ältere Posts ändern sich kaum – vorhandene Werte übernehmen, spart API-Aufrufe
                r = old[mid]
                rows.append({**r, "type": r.get("type") or kind,
                             **{m: int(r.get(m) or 0) for m in METRICS + ["score"]}})
                continue
            vals = ig.insights(mid, METRICS)
            row = {**{k: h.get(k, "") for k in ("folder", "title", "pillar", "format", "slot", "posted_at")},
                   "type": kind, "media_id": mid, "weekday": WEEKDAYS[posted.weekday()]}
            row.update({m: int(vals.get(m, 0) or 0) for m in METRICS})
            row["score"] = score(row)
            rows.append(row)
    return rows


def group(rows, key):
    g = defaultdict(list)
    for r in rows:
        g[r[key] or "–"].append(r)
    return g


def summarize(all_rows: list[dict], cfg: dict) -> None:
    state = load_json(STATE_FILE, {})
    reels = [r for r in all_rows if r.get("type") == "reel"]
    rows = [r for r in all_rows if r.get("type", "karussell") != "reel"]  # Uhrzeit-/Säulen-Vergleich nur über Karussells
    min_n = cfg["posting"]["min_posts_per_slot"]
    lines = [f"# Learnings (Stand {now(cfg):%d.%m.%Y}, {len(rows)} ausgewertete Posts)", ""]
    if not rows:
        LEARNINGS_FILE.write_text("\n".join(lines + ["Noch keine Daten."]) + "\n", encoding="utf-8")
        return

    # Uhrzeiten
    slot_stats = {s: (mean(r["reach"] for r in rs), len(rs)) for s, rs in group(rows, "slot").items()}
    eligible = {s: v for s, v in slot_stats.items() if v[1] >= min_n and s in cfg["posting"]["slots"]}
    if len(eligible) >= 2:
        state["best_slots"] = sorted(eligible, key=lambda s: eligible[s][0], reverse=True)
    lines.append("## Uhrzeiten (Ø Reichweite, Anzahl)")
    lines += [f"- {s}: {v[0]:.0f} ({v[1]})" for s, v in sorted(slot_stats.items(), key=lambda x: -x[1][0])]
    if len(eligible) < 2:
        lines.append(f"- Noch zu wenig Daten für einen Vergleich (mind. {min_n} Posts pro Uhrzeit).")

    # Säulen → Gewichtungsfaktor 0,5–2,0
    overall = mean(r["score"] for r in rows) or 1
    lines += ["", "## Content-Säulen (Ø Score, Anzahl)"]
    factors = {}
    for p, rs in sorted(group(rows, "pillar").items(), key=lambda x: -mean(r["score"] for r in x[1])):
        avg = mean(r["score"] for r in rs)
        lines.append(f"- {p}: {avg:.0f} ({len(rs)})")
        if len(rs) >= 3:
            factors[p] = round(max(0.5, min(2.0, avg / overall)), 2)
    state["pillar_factor"] = factors

    # Formate
    fmt = group(rows, "format")
    if len(fmt) > 1:
        lines += ["", "## Formate (Ø Score, Anzahl)"]
        lines += [f"- {f}: {mean(r['score'] for r in rs):.0f} ({len(rs)})"
                  for f, rs in sorted(fmt.items(), key=lambda x: -mean(r["score"] for r in x[1]))]

    top = sorted(rows, key=lambda r: r["score"], reverse=True)
    lines += ["", "## Top-Posts – Richtung beibehalten, aber nicht kopieren"]
    lines += [f"- „{r['title']}“ ({r['pillar']}, {r['format'] or '–'}): {r['shares']} Shares, {r['saved']} Saves, Reichweite {r['reach']}"
              for r in top[:5]]
    if len(top) >= 8:
        lines += ["", "## Flops – diese Richtung meiden"]
        lines += [f"- „{r['title']}“ ({r['pillar']}, {r['format'] or '–'})" for r in top[-3:]]

    if reels:
        lines += ["", "## Reels vs. Karussells (Ø Reichweite, Anzahl)",
                  f"- Karussells: {mean(r['reach'] for r in rows):.0f} ({len(rows)})",
                  f"- Reels: {mean(r['reach'] for r in reels):.0f} ({len(reels)})"]
    LEARNINGS_FILE.write_text("\n".join(lines) + "\n", encoding="utf-8")
    save_json(STATE_FILE, state)


def main() -> None:
    cfg = load_config()
    rows = fetch(cfg)
    with open(INSIGHTS_CSV, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(rows)
    summarize(rows, cfg)
    print(LEARNINGS_FILE.read_text(encoding="utf-8"))


if __name__ == "__main__":
    main()
