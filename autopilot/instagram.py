"""Schlanker Client für die Instagram API.

Unterstützt beide Zugänge, die Meta anbietet – erkannt am Token:
  IG…   Instagram-Login (ältere Apps)      → graph.instagram.com, Token läuft nach 60 Tagen ab
  EAA…  Unified Login (neue Apps ab 2026)  → graph.facebook.com, System-User-Token ohne Ablauf
"""
from __future__ import annotations

import os
import time

import requests


class InstagramError(RuntimeError):
    pass


def is_unified(token: str) -> bool:
    return token.strip().startswith("EAA")


class Instagram:
    def __init__(self, cfg: dict, token: str | None = None, user_id: str | None = None):
        ig = cfg["instagram"]
        self.token = token or os.environ.get("IG_ACCESS_TOKEN", "").strip()
        if not self.token:
            raise SystemExit("Fehlende Umgebungsvariable IG_ACCESS_TOKEN.")
        self.unified = is_unified(self.token)
        if self.unified:
            host = ig.get("api_host_unified", "https://graph.facebook.com")
            version = ig.get("api_version_unified", "v26.0")
        else:
            host, version = ig["api_host"], ig["api_version"]
        self.base = f"{host.rstrip('/')}/{version}"
        self._user_id = user_id or os.environ.get("IG_USER_ID", "").strip()

    @property
    def user_id(self) -> str:
        """ID des Instagram-Kontos. Beim Instagram-Login reicht „me“, beim Unified
        Login wird sie einmalig über die Konten ermittelt, die dem Token zugewiesen sind."""
        if not self._user_id:
            if not self.unified:
                self._user_id = "me"
            else:
                accounts = self.find_accounts()
                if not accounts:
                    raise SystemExit("Kein Instagram-Konto für diesen Token gefunden. In der Meta-App prüfen, "
                                     "ob @kollege.ki der App zugewiesen ist, oder IG_USER_ID als Secret setzen.")
                if len(accounts) > 1:
                    names = ", ".join(f"@{a.get('username')} ({a['id']})" for a in accounts)
                    raise SystemExit(f"Mehrere Instagram-Konten gefunden: {names}. IG_USER_ID als Secret setzen.")
                self._user_id = accounts[0]["id"]
        return self._user_id

    def find_accounts(self) -> list[dict]:
        """Instagram-Konten, auf die ein Unified-Login-Token Zugriff hat."""
        found: dict[str, dict] = {}
        attempts = [
            ("me/assigned_instagram_accounts", {"fields": "id,username"}, lambda d: d.get("data", [])),
            ("me/accounts", {"fields": "instagram_business_account{id,username}"},
             lambda d: [p["instagram_business_account"] for p in d.get("data", []) if p.get("instagram_business_account")]),
        ]
        for path, params, extract in attempts:
            try:
                for acc in extract(self.get(path, **params)):
                    if acc.get("id"):
                        found[acc["id"]] = acc
            except InstagramError:
                continue
        return list(found.values())

    def account_info(self) -> dict:
        return self.get(self.user_id, fields="id,username,followers_count,media_count")

    def _req(self, method: str, path: str, **params):
        params["access_token"] = self.token
        url = f"{self.base}/{path.lstrip('/')}"
        for attempt in range(3):
            if method == "GET":
                r = requests.get(url, params=params, timeout=60)
            else:
                r = requests.post(url, data=params, timeout=120)
            if r.status_code < 500:
                break
            time.sleep(5 * (attempt + 1))
        data = r.json() if r.content else {}
        if r.status_code >= 400 or "error" in data:
            err = data.get("error", {})
            raise InstagramError(f"{r.status_code} {err.get('message', r.text[:300])} "
                                 f"(code {err.get('code')}, subcode {err.get('error_subcode')})")
        return data

    def get(self, path, **p):
        return self._req("GET", path, **p)

    def post(self, path, **p):
        return self._req("POST", path, **p)

    def wait_ready(self, container_id: str, timeout: int = 300) -> None:
        start = time.time()
        while True:
            info = self.get(container_id, fields="status_code,status")
            status = info.get("status_code")
            if status == "FINISHED":
                return
            if status in ("ERROR", "EXPIRED"):
                raise InstagramError(f"Container {container_id} Status {status}: {info.get('status', '')}")
            if time.time() - start > timeout:
                raise InstagramError(f"Container {container_id} nach {timeout}s nicht fertig ({status})")
            time.sleep(5)

    def publish_carousel(self, image_urls: list[str], caption: str) -> str:
        if not 2 <= len(image_urls) <= 10:
            raise InstagramError(f"Karussell braucht 2–10 Bilder, hat {len(image_urls)}")
        children = []
        for url in image_urls:
            c = self.post(f"{self.user_id}/media", image_url=url, is_carousel_item="true")
            children.append(c["id"])
        for cid in children:
            self.wait_ready(cid)
        parent = self.post(f"{self.user_id}/media", media_type="CAROUSEL",
                           children=",".join(children), caption=caption)
        self.wait_ready(parent["id"])
        published = self.post(f"{self.user_id}/media_publish", creation_id=parent["id"])
        return published["id"]

    def publish_reel(self, video_path, caption: str, share_to_feed: bool = False,
                     thumb_offset_ms: int | None = None, video_url: str | None = None) -> str:
        """Reel per „resumable upload“: Container anlegen, Video direkt zu Meta hochladen,
        auf die Verarbeitung warten, veröffentlichen. Lehnt Meta den Upload ab
        (ProcessingFailedError) und ist video_url gesetzt, holt sich Instagram das Video
        in einem neuen Container selbst von dieser öffentlichen URL."""
        from pathlib import Path

        video = Path(video_path)
        base_params = {"media_type": "REELS", "caption": caption,
                       "share_to_feed": "true" if share_to_feed else "false"}
        if thumb_offset_ms is not None:
            base_params["thumb_offset"] = str(thumb_offset_ms)
        try:
            container = self.post(f"{self.user_id}/media", upload_type="resumable", **base_params)
            cid = container["id"]
            version = self.base.rsplit("/", 1)[-1]
            uri = container.get("uri") or f"https://rupload.facebook.com/ig-api-upload/{version}/{cid}"
            data = video.read_bytes()
            r = requests.post(uri, data=data, timeout=600, headers={
                "Authorization": f"OAuth {self.token}", "offset": "0", "file_size": str(len(data))})
            if r.status_code >= 400:
                raise InstagramError(f"Video-Upload fehlgeschlagen: {r.status_code} {r.text[:300]}")
            self.wait_ready(cid, timeout=900)
        except InstagramError as e:
            if not video_url:
                raise
            print(f"Direkt-Upload abgelehnt ({str(e)[:120]}) – neuer Versuch über {video_url}", flush=True)
            container = self.post(f"{self.user_id}/media", video_url=video_url, **base_params)
            cid = container["id"]
            self.wait_ready(cid, timeout=900)
        published = self.post(f"{self.user_id}/media_publish", creation_id=cid)
        return published["id"]

    def publishing_quota(self) -> dict:
        data = self.get(f"{self.user_id}/content_publishing_limit", fields="config,quota_usage")
        return (data.get("data") or [{}])[0]

    def permalink(self, media_id: str) -> str:
        try:
            return self.get(media_id, fields="permalink").get("permalink", "")
        except InstagramError:
            return ""

    def insights(self, media_id: str, metrics: list[str]) -> dict:
        """Holt Insights; fragt bei Fehlern jede Metrik einzeln ab."""
        def parse(data):
            out = {}
            for m in data.get("data", []):
                if "total_value" in m:
                    out[m["name"]] = m["total_value"].get("value", 0)
                elif m.get("values"):
                    out[m["name"]] = m["values"][0].get("value", 0)
            return out
        try:
            return parse(self.get(f"{media_id}/insights", metric=",".join(metrics)))
        except InstagramError:
            result = {}
            for m in metrics:
                try:
                    result.update(parse(self.get(f"{media_id}/insights", metric=m)))
                except InstagramError:
                    pass
            return result
