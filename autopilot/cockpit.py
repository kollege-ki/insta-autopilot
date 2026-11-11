"""Projektcockpit: eine Seite (docs/index.html, über GitHub Pages abrufbar), die zeigt
  – was gerade passiert (Ampel, letzter/nächster Post, Queue, offene Freigaben)
  – was als Nächstes zu tun ist (automatisch abgeleitet + Setup-Checkliste + Roadmap)
  – wie der Verlauf ist (Follower, Reichweite, Meilensteine und ihre Wirkung, Aktivität)

Wird aufgerufen von stats.py (täglich), nach jedem Post und bei jeder Freigabe.
"""
from __future__ import annotations

import html
import json
import os
import re
import subprocess
from datetime import date, datetime, timedelta
from statistics import mean

from .common import CONTENT, DATA, HISTORY_FILE, ROOT, load_config, load_json, now, queue_items

DASHBOARD = ROOT / "docs" / "index.html"
E = html.escape


# ---------------------------------------------------------------- Daten

def open_prs() -> list[dict] | None:
    """Offene Freigabe-PRs über die gh-CLI (im Workflow vorhanden). None = unbekannt."""
    if not os.environ.get("GH_TOKEN"):
        return None
    try:
        out = subprocess.run(["gh", "pr", "list", "--state", "open", "--json", "number,title,url,createdAt",
                              "--repo", os.environ.get("GITHUB_REPOSITORY", "")],
                             capture_output=True, text=True, timeout=60, check=True).stdout
        return json.loads(out)
    except Exception:  # noqa: BLE001
        return None


def repo_url() -> str:
    repo = os.environ.get("GITHUB_REPOSITORY")
    return f"https://github.com/{repo}" if repo else ""


def journal_last_date() -> date | None:
    p = CONTENT / "journal.md"
    if not p.exists():
        return None
    dates = [date(int(y), int(m), int(d)) for d, m, y in re.findall(r"^##\s*(\d{2})\.(\d{2})\.(\d{4})", p.read_text(encoding="utf-8"), re.M)]
    return max(dates) if dates else None


def next_post_time(cfg, history) -> datetime | None:
    from .publish import parse_slot, slots_for_day

    t = now(cfg)
    for offset in range(3):
        d = t.date() + timedelta(days=offset)
        done = len([h for h in history if h["posted_at"][:10] == d.isoformat()])
        slots, _ = slots_for_day(cfg, d)
        for s in slots[done:]:
            dt = datetime.combine(d, parse_slot(s), tzinfo=t.tzinfo)
            if dt > t - timedelta(minutes=30) or offset > 0:
                return dt
    return None


def fmt_dt(dt: datetime | None) -> str:
    if not dt:
        return "–"
    today = now(load_config()).date()
    if dt.date() == today:
        return f"heute {dt:%H:%M}"
    if dt.date() == today + timedelta(days=1):
        return f"morgen {dt:%H:%M}"
    return f"{dt:%d.%m.%Y %H:%M}"


# ---------------------------------------------------------------- Logik

def setup_steps(cfg, history, items, insights_rows) -> list[tuple[str, bool]]:
    env = os.environ
    known = "HAS_ANTHROPIC" in env
    return [
        ("Name und Handle in config.yaml eingetragen", cfg["brand"]["handle"] not in ("@deinhandle", "")),
        ("Secrets eingetragen (Claude, Instagram, GitHub-Token)",
         known and all(env.get(k) == "true" for k in ("HAS_ANTHROPIC", "HAS_IG", "HAS_PAT"))),
        ("Erste Posts generiert und freigegeben", bool(items or history)),
        ("Erster Post veröffentlicht", bool(history)),
        ("Erste Insights ausgewertet (24 h nach dem 1. Post)", bool(insights_rows)),
    ]


def roadmap_status(cfg, followers, n_posts) -> list[dict]:
    out = []
    for r in cfg.get("roadmap", []):
        if "followers" in r:
            cur, goal, unit = followers, r["followers"], "Follower"
        else:
            cur, goal, unit = n_posts, r.get("posts", 0), "Posts"
        out.append({**r, "cur": cur, "goal": goal, "unit": unit, "done": cur >= goal,
                    "pct": 100 if goal == 0 else min(100, round(cur / goal * 100))})
    return out


def todos(cfg, history, items, prs, setup, roadmap) -> list[tuple[str, str, str]]:
    """(Priorität, Text, Link) – rot = jetzt, gelb = bald, grau = Info."""
    t, base = [], repo_url()
    ppd = cfg["posting"]["posts_per_day"]
    for p in prs or []:
        urgent = len(items) / ppd <= 1
        t.append(("rot" if urgent else "gelb", f"Freigeben: {p['title']}", p["url"]))
    if not items and history:
        t.append(("rot", "Queue ist leer – es wird nichts gepostet. Content generieren.", f"{base}/actions/workflows/generate.yml"))
    elif len(items) / ppd <= 2 and not prs and history:
        t.append(("gelb", f"Queue reicht nur noch {len(items) / ppd:.0f} Tag(e) – Content generieren.",
                  f"{base}/actions/workflows/generate.yml"))
    if history:
        last = datetime.fromisoformat(history[-1]["posted_at"])
        if now(cfg) - last > timedelta(hours=48):
            t.append(("rot", "Seit über 48 h kein Post – Workflow „2 · Posten“ prüfen.", f"{base}/actions/workflows/publish.yml"))
    jd = journal_last_date()
    if jd and (now(cfg).date() - jd).days > 7:
        t.append(("gelb", f"Journal seit {(now(cfg).date() - jd).days} Tagen nicht ergänzt – kurz Stichworte eintragen.",
                  f"{base}/edit/main/content/journal.md"))
    for name, done in setup:
        if not done:
            t.append(("gelb", f"Setup: {name}", f"{base}#readme"))
            break
    nxt = next((r for r in roadmap if not r["done"]), None)
    if nxt:
        t.append(("grau", f"Nächstes Etappenziel: {nxt['title']} (bei {nxt['goal']} {nxt['unit']}) – {nxt['todo']}", ""))
    if history and len(history) % 30 in range(0, 3) and len(history) >= 30:
        t.append(("grau", "30 Posts geschafft: Learnings lesen und Frequenz prüfen.", f"{base}/blob/main/data/learnings.md"))
    return t


def ampel(todo_list, history) -> tuple[str, str]:
    if any(p == "rot" for p, _, _ in todo_list):
        return "rot", "Handlungsbedarf"
    if not history:
        return "gelb", "Im Aufbau"
    if any(p == "gelb" for p, _, _ in todo_list):
        return "gelb", "Läuft – bald etwas zu tun"
    return "gruen", "Läuft von selbst"


def activity(history, ms, items) -> list[tuple[str, str]]:
    ev = []
    for h in history[-10:]:
        ev.append((h["posted_at"][:16], f"Gepostet: „{h['title']}“"))
    for m in ms[-10:]:
        ev.append((m["date"], f"Meilenstein: {m['title']}"))
    stamps = sorted({i.name[:15] for i in items})
    for s in stamps[-5:]:
        try:
            dt = datetime.strptime(s, "%Y-%m-%d-%H%M")
            ev.append((dt.isoformat(timespec="minutes"), "Neue Posts generiert und freigegeben"))
        except ValueError:
            pass
    return sorted(ev, reverse=True)[:8]


# ---------------------------------------------------------------- Seite

def build() -> None:
    from .stats import IMPACT, MILESTONES, fol_txt, fmt_date, impact, load_daily, load_posts, pct, svg_bars, svg_line, WINDOW

    cfg = load_config()
    c = cfg["brand"]["colors"]
    history = load_json(HISTORY_FILE, [])
    items = queue_items()
    ms = load_json(MILESTONES, [])
    posts, daily = load_posts(), load_daily()
    rows = impact(ms, posts, daily)
    prs = open_prs()
    followers = daily[-1]["followers"] if daily else 0
    setup = setup_steps(cfg, history, items, posts)
    road = roadmap_status(cfg, followers, len(history))
    todo_list = todos(cfg, history, items, prs, setup, road)
    color, status = ampel(todo_list, history)
    n_open = len([x for x in todo_list if x[0] != "grau"])
    ppd = cfg["posting"]["posts_per_day"]
    t = now(cfg)

    last = history[-1] if history else None
    nxt_item = json.loads((items[0] / "post.json").read_text(encoding="utf-8")) if items else None
    nxt_time = next_post_time(cfg, history) if items else None
    queue_until = (t.date() + timedelta(days=len(items) / ppd)) if items else None
    f7 = next((r["followers"] for r in daily if r["d"] >= t.date() - timedelta(days=7)), None)

    amp = {"rot": "#FF6B6B", "gelb": "#FFD166", "gruen": c["accent"]}[color]
    prio = {"rot": "#FF6B6B", "gelb": "#FFD166", "grau": c["muted"]}

    def card(title, value, sub=""):
        return f'<div class="card"><span class="muted">{title}</span><b>{value}</b><span class="muted">{sub}</span></div>'

    now_cards = "".join([
        card("Letzter Post", E(last["title"]) if last else "noch keiner",
             (f'{fmt_dt(datetime.fromisoformat(last["posted_at"]))}' + (f' · <a href="{E(last["permalink"])}">ansehen</a>' if last.get("permalink") else "")) if last else ""),
        card("Nächster Post", E(nxt_item["title"]) if nxt_item else "Queue leer", fmt_dt(nxt_time) if nxt_item else ""),
        card("Queue", f"{len(items)} Posts", f"reicht bis {queue_until:%d.%m.}" if queue_until else "–"),
        card("Freigaben offen", "?" if prs is None else len(prs), "Pull Requests"),
    ])
    kpi_cards = "".join([
        card("Follower", followers if daily else "–", f"+{followers - f7} in 7 Tagen" if f7 is not None and daily else ""),
        card("Posts gesamt", len(history), ""),
        card("Ø Reichweite", f"{mean(p['reach'] for p in posts):.0f}" if posts else "–", "pro Post"),
        card("Meilensteine", len(ms), ""),
    ])
    def linked(txt, link):
        return f'<a href="{E(link)}">{E(txt)}</a>' if link else E(txt)

    todo_html = "".join(f'<li><span class="dot" style="background:{prio[p]}"></span>{linked(txt, link)}</li>'
                        for p, txt, link in todo_list) or "<li>Nichts zu tun – läuft. 🎉</li>"
    setup_html = "" if all(d for _, d in setup) else (
        "<h2>Setup</h2><ul class='check'>" + "".join(f"<li>{'✅' if d else '⬜️'} {E(n)}</li>" for n, d in setup) + "</ul>")
    road_html = "".join(
        f'<div class="road"><div><b>{"✅ " if r["done"] else ""}{E(r["title"])}</b>'
        f'<span class="muted"> · {r["cur"]}/{r["goal"]} {r["unit"]}</span><br><span class="muted">{E(r["todo"])}</span></div>'
        f'<div class="bar"><i style="width:{r["pct"]}%"></i></div></div>' for r in road)
    impact_html = "".join(
        f"<tr><td>{fmt_date(r['date'])}</td><td>{E(r['title'])}"
        f"{'<br><span class=muted>' + E(r['details']) + '</span>' if r['details'] and r['source'] == 'auto' and r['title'] != 'Tracking gestartet' else ''}</td>"
        f"<td>{pct(r.get('reach_pre'), r.get('reach_post')) if 'reach_pre' in r else '<span class=muted>zu wenig Daten</span>'}</td>"
        f"<td>{fol_txt(r)}</td></tr>" for r in reversed(rows))
    def when(ts):
        if len(ts) == 10:  # nur Datum (Meilenstein)
            return f"{date.fromisoformat(ts):%d.%m.%Y}"
        return fmt_dt(datetime.fromisoformat(ts).replace(tzinfo=t.tzinfo))

    act_html = "".join(f"<li><span class='muted'>{when(ts)}</span> {E(txt)}</li>"
                       for ts, txt in activity(history, ms, items)) or "<li class='muted'>Noch keine Aktivität.</li>"
    base = repo_url()
    links = " · ".join(f'<a href="{base}/{p}">{n}</a>' for n, p in [
        ("Freigaben", "pulls"), ("Workflows", "actions"), ("Journal", "edit/main/content/journal.md"),
        ("Einstellungen", "edit/main/config.yaml"), ("Learnings", "blob/main/data/learnings.md")]) if base else ""

    page = f"""<!DOCTYPE html>
<html lang="de"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="robots" content="noindex"><title>Cockpit · {E(cfg['brand']['name'])}</title>
<style>
*{{box-sizing:border-box}}
body{{margin:0;background:{c['background']};color:{c['text']};font:16px/1.5 Inter,system-ui,-apple-system,sans-serif}}
main{{max-width:1000px;margin:0 auto;padding:24px 18px 60px}}
a{{color:{c['accent']};text-decoration:none}} a:hover{{text-decoration:underline}}
h1{{font-size:24px;margin:0}} h2{{font-size:17px;margin:36px 0 12px;letter-spacing:.02em}}
.muted{{color:{c['muted']};font-size:14px}}
.status{{display:flex;align-items:center;gap:14px;background:{c['surface']};border-radius:16px;padding:16px 18px;margin-top:18px}}
.lamp{{width:18px;height:18px;border-radius:50%;background:{amp};box-shadow:0 0 18px {amp}}}
.status b{{font-size:20px}}
.grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(160px,1fr));gap:12px}}
.card{{background:{c['surface']};border-radius:14px;padding:14px 16px;display:flex;flex-direction:column;gap:2px;min-width:0}}
.card b{{font-size:18px;line-height:1.3;hyphens:auto;overflow-wrap:break-word}}
ul{{list-style:none;padding:0;margin:0}} .todo li,.check li,.act li{{background:{c['surface']};border-radius:12px;padding:11px 14px;margin-bottom:8px}}
.dot{{display:inline-block;width:10px;height:10px;border-radius:50%;margin-right:10px}}
.road{{background:{c['surface']};border-radius:12px;padding:12px 14px;margin-bottom:8px}}
.bar{{height:6px;background:{c['background']};border-radius:3px;margin-top:8px;overflow:hidden}} .bar i{{display:block;height:100%;background:{c['accent']}}}
svg{{width:100%;height:auto;background:{c['surface']};border-radius:14px}}
table{{width:100%;border-collapse:collapse;font-size:15px;table-layout:fixed}} td{{overflow-wrap:anywhere}} body{{overflow-x:hidden}} td,th{{text-align:left;padding:10px 8px;border-bottom:1px solid {c['surface']};vertical-align:top}}
th{{color:{c['muted']};font-weight:600}}
.cols{{display:grid;grid-template-columns:1fr 1fr;gap:24px}} @media(max-width:760px){{.cols{{grid-template-columns:1fr}}}}
</style></head><body><main>
<h1>Cockpit · {E(cfg['brand']['name'])}</h1>
<div class="muted">{E(cfg['brand']['handle'])} · Stand {t:%d.%m.%Y %H:%M}{' · ' + links if links else ''}</div>
<div class="status"><div class="lamp"></div><div><b>{status}</b><br><span class="muted">{n_open} {"offener Punkt" if n_open == 1 else "offene Punkte"}</span></div></div>

<h2>Jetzt</h2><div class="grid">{now_cards}</div>
<div class="cols">
 <div><h2>Nächste Schritte</h2><ul class="todo">{todo_html}</ul>{setup_html}</div>
 <div><h2>Roadmap</h2>{road_html or '<p class="muted">Keine Roadmap in config.yaml.</p>'}</div>
</div>

<h2>Verlauf</h2><div class="grid">{kpi_cards}</div>
<h2>Follower <span class="muted">(gestrichelt = Meilenstein)</span></h2>{svg_line(daily, ms, c)}
<h2>Reichweite pro Post <span class="muted">(letzte 40)</span></h2>{svg_bars(posts, c)}
<h2>Was hat wie viel gebracht?</h2>
<p class="muted">Je {WINDOW} Tage vor und nach dem Meilenstein. Zusammenhang, kein Beweis.</p>
<table><tr><th>Datum</th><th>Meilenstein</th><th>Reichweite/Post</th><th>Follower/Tag</th></tr>{impact_html}</table>
<h2>Letzte Aktivität</h2><ul class="act">{act_html}</ul>
</main></body></html>"""
    DASHBOARD.parent.mkdir(exist_ok=True)
    DASHBOARD.write_text(page, encoding="utf-8")
    print(f"Cockpit: {status} · offen: {n_open} → {DASHBOARD}")


if __name__ == "__main__":
    build()
