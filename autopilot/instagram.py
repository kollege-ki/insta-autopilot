"""Schlanker Client für die Instagram API (mit Instagram-Login)."""
from __future__ import annotations

import os
import time

import requests


class InstagramError(RuntimeError):
    pass


class Instagram:
    def __init__(self, cfg: dict, token: str | None = None, user_id: str | None = None):
        ig = cfg["instagram"]
        self.base = f"{ig['api_host'].rstrip('/')}/{ig['api_version']}"
        self.token = token or os.environ.get("IG_ACCESS_TOKEN", "").strip()
        self.user_id = user_id or os.environ.get("IG_USER_ID", "").strip() or "me"
        if not self.token:
            raise SystemExit("Fehlende Umgebungsvariable IG_ACCESS_TOKEN.")

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
            status = self.get(container_id, fields="status_code").get("status_code")
            if status == "FINISHED":
                return
            if status in ("ERROR", "EXPIRED"):
                raise InstagramError(f"Container {container_id} Status {status}")
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
