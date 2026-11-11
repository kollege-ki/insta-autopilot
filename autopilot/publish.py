"""Postet den nächsten freigegebenen Post aus queue/ – aber nur, wenn gerade
der richtige Zeit-Slot dran ist. Läuft im Workflow alle 30 Minuten.

Slot-Logik:
  explore – die Uhrzeiten aus config.yaml rotieren täglich (sammelt Daten)
  auto    – beste Uhrzeit laut Insights; jeden 5. Tag wird trotzdem rotiert,
            damit sich die Auswertung an Veränderungen anpasst
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
from datetime import datetime, time as dtime, timedelta

from .common import (HISTORY_FILE, POSTED, STATE_FILE, gh_warning, load_config, load_json,
                     now, queue_items, save_json)


def parse_slot(s: str) -> dtime:
    h, m = s.split(":")
    return dtime(int(h), int(m))


def slots_for_day(cfg: dict, day) -> tuple[list[str], str]:
    p = cfg["posting"]
    slots = list(p["slots"])
    k = p["posts_per_day"]
    rot = day.toordinal() % len(slots)
    rotated = slots[rot:] + slots[:rot]
    best = load_json(STATE_FILE, {}).get("best_slots") or []
    if p["mode"] == "auto" and best and day.toordinal() % 5 != 0:
        chosen = (best + [s for s in rotated if s not in best])[:k]
        reason = "auto (beste Uhrzeit laut Insights)"
    else:
        chosen = rotated[:k]
        reason = "explore (Uhrzeiten werden getestet)"
    return sorted(chosen), reason


def image_base_url(cfg: dict) -> str:
    base = cfg["instagram"].get("public_base_url", "").strip()
    if base:
        return base.rstrip("/")
    repo = os.environ.get("GITHUB_REPOSITORY")
    branch = os.environ.get("GITHUB_REF_NAME", "main")
    if not repo:
        raise SystemExit("Keine public_base_url gesetzt und kein GITHUB_REPOSITORY – Bilder-URL unbekannt.")
    return f"https://raw.githubusercontent.com/{repo}/{branch}"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true", help="Sofort posten, Slot-Logik ignorieren")
    ap.add_argument("--dry-run", action="store_true", help="Nur anzeigen, nichts posten")
    args = ap.parse_args()

    cfg = load_config()
    tz_now = now(cfg)
    today = tz_now.date()
    history = load_json(HISTORY_FILE, [])
    posted_today = [h for h in history if h["posted_at"][:10] == today.isoformat()]

    slots, reason = slots_for_day(cfg, today)
    print(f"Jetzt {tz_now:%d.%m.%Y %H:%M} · heutige Slots {slots} · Modus {reason} · heute gepostet: {len(posted_today)}")

    slot = None
    if not args.force:
        if len(posted_today) >= cfg["posting"]["posts_per_day"]:
            print("Heute schon fertig gepostet.")
            return
        slot = slots[len(posted_today)]
        if tz_now.time() < parse_slot(slot):
            print(f"Nächster Slot {slot} ist noch nicht erreicht.")
            return
        if history:
            last = datetime.fromisoformat(history[-1]["posted_at"])
            if tz_now - last < timedelta(hours=cfg["posting"]["min_hours_between_posts"]):
                print("Mindestabstand zum letzten Post noch nicht erreicht.")
                return

    items = queue_items()
    if not items:
        gh_warning("Queue ist leer – keine freigegebenen Posts. Workflow 'Content generieren' starten oder PR mergen.")
        return
    if len(items) <= 2:
        gh_warning(f"Nur noch {len(items)} Post(s) in der Queue.")

    item = items[0]
    post = json.loads((item / "post.json").read_text(encoding="utf-8"))
    base = image_base_url(cfg)
    urls = [f"{base}/queue/{item.name}/{img}" for img in post["images"]]
    print(f"→ Poste {item.name} ({len(urls)} Slides)")

    if args.dry_run:
        print("Dry-Run – Bild-URLs:\n  " + "\n  ".join(urls))
        print("Caption:\n" + post["caption_final"])
        return

    from .instagram import Instagram  # erst hier, damit Dry-Run ohne Token geht
    ig = Instagram(cfg)
    media_id = ig.publish_carousel(urls, post["caption_final"])
    permalink = ig.permalink(media_id)
    print(f"✓ Veröffentlicht: {media_id} {permalink}")

    post["published"] = {"media_id": media_id, "permalink": permalink,
                         "posted_at": tz_now.isoformat(timespec="minutes"), "slot": slot or "manuell"}
    (item / "post.json").write_text(json.dumps(post, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    POSTED.mkdir(exist_ok=True)
    shutil.move(str(item), str(POSTED / item.name))

    history.append({
        "folder": item.name, "title": post["title"], "pillar": post["pillar"], "format": post.get("format", ""),
        "media_id": media_id, "permalink": permalink,
        "posted_at": tz_now.isoformat(timespec="minutes"), "slot": slot or "manuell",
    })
    save_json(HISTORY_FILE, history)


if __name__ == "__main__":
    main()
