"""Gemeinsame Helfer: Pfade, Config, JSON-Dateien, Zeit."""
from __future__ import annotations

import json
import os
import re
import unicodedata
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import yaml

ROOT = Path(__file__).resolve().parent.parent
QUEUE = ROOT / "queue"
POSTED = ROOT / "posted"
DATA = ROOT / "data"
CONTENT = ROOT / "content"
TMP = ROOT / ".autopilot"

HISTORY_FILE = DATA / "history.json"
STATE_FILE = DATA / "state.json"
LEARNINGS_FILE = DATA / "learnings.md"
INSIGHTS_CSV = DATA / "insights.csv"


def load_config() -> dict:
    with open(ROOT / "config.yaml", encoding="utf-8") as f:
        return yaml.safe_load(f)


def load_json(path: Path, default):
    if not path.exists():
        return default
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def save_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")


def now(cfg: dict) -> datetime:
    return datetime.now(ZoneInfo(cfg["posting"]["timezone"]))


def slugify(text: str, max_len: int = 40) -> str:
    text = (text.replace("ä", "ae").replace("ö", "oe").replace("ü", "ue")
                .replace("Ä", "Ae").replace("Ö", "Oe").replace("Ü", "Ue").replace("ß", "ss"))
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    text = re.sub(r"[^a-zA-Z0-9]+", "-", text).strip("-").lower()
    return text[:max_len].rstrip("-") or "post"


def queue_items() -> list[Path]:
    """Freigegebene, noch nicht gepostete Posts in Reihenfolge."""
    if not QUEUE.exists():
        return []
    return sorted(p for p in QUEUE.iterdir() if p.is_dir() and (p / "post.json").exists())


def require_env(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise SystemExit(f"Fehlende Umgebungsvariable {name} (in GitHub unter Settings → Secrets anlegen).")
    return value


def gh_warning(msg: str) -> None:
    """Warnung, die in GitHub Actions sichtbar markiert wird."""
    print(f"::warning::{msg}" if os.environ.get("GITHUB_ACTIONS") else f"WARNUNG: {msg}")
