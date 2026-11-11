"""Hilfen rund um den Instagram-Zugangstoken.

  python -m autopilot.token_tools whoami          – prüft Token, zeigt Account + Posting-Kontingent
  python -m autopilot.token_tools refresh <datei> – verlängert den Token (60 Tage) und schreibt ihn in <datei>
"""
from __future__ import annotations

import os
import sys

import requests

from .common import load_config


def whoami() -> None:
    from .instagram import Instagram

    cfg = load_config()
    ig = Instagram(cfg)
    me = ig.get("me", fields="user_id,username,account_type,followers_count,media_count")
    print(f"Account: @{me.get('username')} · Typ {me.get('account_type')} · "
          f"{me.get('followers_count')} Follower · {me.get('media_count')} Beiträge")
    print(f"IG_USER_ID für die Secrets: {me.get('user_id')}")
    try:
        q = ig.publishing_quota()
        print(f"Posting-Kontingent: {q.get('quota_usage')} von {q.get('config', {}).get('quota_total')} in 24 h")
    except Exception as e:  # noqa: BLE001
        print(f"Kontingent nicht abrufbar: {e}")


def refresh(out_path: str) -> None:
    token = os.environ.get("IG_ACCESS_TOKEN", "").strip()
    if not token:
        raise SystemExit("Fehlende Umgebungsvariable IG_ACCESS_TOKEN.")
    host = load_config()["instagram"]["api_host"].rstrip("/")
    r = requests.get(f"{host}/refresh_access_token",
                     params={"grant_type": "ig_refresh_token", "access_token": token}, timeout=60)
    data = r.json()
    if "access_token" not in data:
        raise SystemExit(f"Token-Refresh fehlgeschlagen: {data}")
    with open(out_path, "w") as f:
        f.write(data["access_token"])
    print(f"Token verlängert, gültig für weitere {int(data.get('expires_in', 0)) // 86400} Tage.")


if __name__ == "__main__":
    if len(sys.argv) >= 2 and sys.argv[1] == "whoami":
        whoami()
    elif len(sys.argv) >= 3 and sys.argv[1] == "refresh":
        refresh(sys.argv[2])
    else:
        print(__doc__)
