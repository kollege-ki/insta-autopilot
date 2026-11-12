"""Erzeugt einen Batch Karussell-Posts mit Claude in drei Stufen:

  1. Ideen-Runde: viele ungewöhnliche Ideen (Säule × Format × überraschender Dreh),
     jede mit Selbstbewertung „Originalität" und „Nutzen".
  2. Auswahl im Code (beste Ideen, möglichst verschiedene Formate),
     dann schreibt Claude nur die Gewinner aus – bei Tool-, Workflow- und Skill-Posts
     mit Websuche, damit Funktionen, Namen und Preise aktuell stimmen.
  3. Kritik-Runde: Claude prüft jeden Post als strenger Redakteur gegen alle Regeln
     und überarbeitet ihn gezielt.

Danach werden die Slides gerendert und in queue/ abgelegt. Im GitHub-Workflow
wird daraus ein Pull Request zur Freigabe am Handy.
"""
from __future__ import annotations

import argparse
import json
import os
import random
import re
from collections import Counter
from pathlib import Path

import requests

from .common import (CONTENT, HISTORY_FILE, LEARNINGS_FILE, QUEUE, STATE_FILE, TMP,
                     load_config, load_json, now, queue_items, require_env, slugify)
from .render import render_post

API_URL = "https://api.anthropic.com/v1/messages"


# ---------------------------------------------------------------- Prompts

def base_system(cfg: dict) -> str:
    b, c = cfg["brand"], cfg["content"]
    banned = ", ".join(f"„{p}“" for p in c.get("banned_phrases", []))
    topics = "\n".join(f"   - {t}" for t in c.get("banned_topics", []))
    return f"""Du bist Kreativ-Chef und Texter der Instagram-Page „{b['name']}“ ({b['handle']}).

THEMA: Wie man KI so einsetzt, dass sie für einen arbeitet – mit Tools, Prompts und Skills.
Die Page dokumentiert außerdem ihren eigenen Aufbau (Build in Public): Sie wird selbst von einer
KI-Pipeline betrieben (Claude schreibt, ein Script gestaltet, GitHub Actions postet, ein Mensch gibt frei).

SPRACHE: {b['language']}
TON: {b['tone']}

ANSPRUCH: Kein Einheitsbrei. Die DACH-Instagram-Welt ist voll mit identischen „5 KI-Tools“-Karussells.
Jeder Post muss etwas haben, das man so noch nicht gesehen hat: einen überraschenden Dreh,
einen ungewöhnlichen Einsatzzweck, eine konkrete Pointe. Lieber spezifisch und eigen als breit und brav.
Test für jede Idee: Würde jemand, der täglich KI-Content sieht, beim Wischen hängen bleiben?

HARTE REGELN – niemals brechen:
1. Keine Finanz-, Anlage-, Steuer- oder Rechtstipps. Nichts zu Aktien, Krypto, Trading.
2. Keine Einkommens- oder Erfolgsversprechen.
3. Keine erfundenen Zahlen, Erfahrungen, Kundenstimmen oder Ergebnisse. Erlebnisse und Zahlen der Page
   NUR aus dem Journal und den gemessenen Stats. Sonst als Anleitung/Experiment zum Selbermachen formulieren, nicht als „ich habe“.
4. Preise, Versionsnummern, Limits oder Feature-Details von Tools nur, wenn sie per Websuche
   bestätigt sind (Quelle in review_notes) – sonst weglassen. Ohne Websuche: nur, wenn du dir sicher bist,
   und dann in review_notes vermerken. Dein Wissen kann veraltet sein, Tools ändern sich laufend.
5. Jeder Post hat einen konkreten, sofort nachmachbaren Nutzen. Kein Clickbait, den der Inhalt nicht einlöst.
6. Verbotene Floskeln: {banned}
7. Verbotene Themen:
{topics}
"""


FORMAT_RULES = """FORMAT PRO POST:
- Slide 1 (Cover): headline = Hook, max. ca. 10 Wörter, erzeugt eine offene Frage, die erst Slide 2+ beantwortet.
  body optional: 1 kurzer Satz, der neugierig macht – keine Inhaltsangabe des Posts.
- Weitere Slides: headline max. ca. 7 Wörter, body max. ca. 25 Wörter. Ein Gedanke pro Slide.
- Prompts, Skill-Texte oder Beispiele zum Kopieren ins Feld "box" (max. ca. 50 Wörter). Listen in der box knapp
  im Stil „Termin fehlt → nächster Dienstag“, keine ganzen Sätze.
- Markiere pro Slide 1–2 Schlüsselwörter mit *Sternchen* (werden in der Akzentfarbe gesetzt). Nie ganze Sätze markieren.
- {smin} bis {smax} Slides. Eine Abschluss-Slide mit Follow-Aufruf wird automatisch angehängt – NICHT selbst schreiben.
- caption: 2–5 kurze Absätze, bringt einen Zusatz-Gedanken (nicht nur Wiederholung), endet mit einer
  konkreten Frage an die Community. Keine Hashtags in der caption.
- hashtags: 3–{hmax} spezifische Hashtags ohne #-Zeichen.
- review_notes: alles, was ein Mensch vor dem Posten prüfen sollte. Leer lassen, wenn nichts.

SPRACHSTIL – so, wie ein kluger Kollege beim Kaffee redet:
- Kurze Sätze. Verben statt Hauptwörter („Sie erfindet“ statt „Lücken werden still gefüllt“).
- Aktiv und direkt, Du-Form. Gerne mal ein Gedankenstrich oder eine knappe Pointe.
- Keine Labels wie „Der Fehler:“, „Beispiel:“, „Schwäche 1:“, „Schritt 2:“ vor die Headline setzen –
  die Headline sagt die Sache selbst.
- Nenne NIE die internen Namen von Säulen oder Formaten im Text (z. B. „Tool-Check“, „Rückwärts“, „Rezept“,
  „Mythos vs. Realität“) – das Format wird gezeigt, nicht angekündigt.
- Kein Erklär-Deutsch, keine Schachtelsätze, keine Füllwörter („eigentlich“, „grundsätzlich“, „im Prinzip“)."""


def context_block(cfg: dict) -> str:
    journal_path = CONTENT / "journal.md"
    journal = journal_path.read_text(encoding="utf-8")[-6000:] if journal_path.exists() else ""
    learnings = LEARNINGS_FILE.read_text(encoding="utf-8")[-3000:] if LEARNINGS_FILE.exists() else "Noch keine Daten."
    titles = "\n".join(f"- {t}" for t in recent_titles()) or "- (noch keine)"
    from .stats import stats_summary
    return f"""ECHTE ZAHLEN DER PAGE (automatisch gemessen – dürfen in Making-of-Posts genannt werden, nur so wie sie hier stehen):
<stats>
{stats_summary(cfg)}
</stats>

JOURNAL DES BETREIBERS (einzige Quelle für Erlebnisse und Zahlen der Page):
<journal>
{journal}
</journal>

WAS BISHER GUT/SCHLECHT LIEF (automatisch aus Instagram-Insights):
<learnings>
{learnings}
</learnings>

BEREITS VERWENDETE THEMEN – nicht wiederholen, auch nicht leicht umformuliert:
{titles}

Heute ist der {now(cfg).strftime('%d.%m.%Y')}."""


# ---------------------------------------------------------------- Tools (Schemas)

def ideas_tool(cfg: dict) -> dict:
    c = cfg["content"]
    return {
        "name": "submit_ideas",
        "description": "Gibt die gesammelten Post-Ideen zurück.",
        "input_schema": {
            "type": "object",
            "properties": {"ideas": {"type": "array", "items": {
                "type": "object",
                "properties": {
                    "pillar": {"type": "string", "enum": [p["id"] for p in c["pillars"]]},
                    "format": {"type": "string", "enum": [f["id"] for f in c["formats"]]},
                    "title": {"type": "string", "description": "Arbeitstitel"},
                    "twist": {"type": "string", "description": "Der überraschende Dreh in einem Satz"},
                    "why_not_generic": {"type": "string", "description": "Warum das kein Einheitsbrei ist"},
                    "originality": {"type": "integer", "minimum": 1, "maximum": 10},
                    "usefulness": {"type": "integer", "minimum": 1, "maximum": 10},
                },
                "required": ["pillar", "format", "title", "twist", "why_not_generic", "originality", "usefulness"],
            }}},
            "required": ["ideas"],
        },
    }


def posts_tool(cfg: dict) -> dict:
    c = cfg["content"]
    return {
        "name": "submit_posts",
        "description": "Gibt die fertigen Karussell-Posts zurück.",
        "input_schema": {
            "type": "object",
            "properties": {"posts": {"type": "array", "items": {
                "type": "object",
                "properties": {
                    "pillar": {"type": "string", "enum": [p["id"] for p in c["pillars"]]},
                    "format": {"type": "string", "enum": [f["id"] for f in c["formats"]]},
                    "title": {"type": "string"},
                    "slides": {"type": "array", "minItems": c["slides_min"], "maxItems": c["slides_max"],
                               "items": {"type": "object", "properties": {
                                   "headline": {"type": "string"},
                                   "body": {"type": "string"},
                                   "box": {"type": "string"}},
                                   "required": ["headline"]}},
                    "caption": {"type": "string"},
                    "hashtags": {"type": "array", "items": {"type": "string"}},
                    "review_notes": {"type": "string"},
                },
                "required": ["pillar", "format", "title", "slides", "caption", "hashtags"],
            }}},
            "required": ["posts"],
        },
    }


# ---------------------------------------------------------------- Logik

class TruncatedError(RuntimeError):
    pass


class UnusableError(RuntimeError):
    pass


def valid_post(post) -> bool:
    return (isinstance(post, dict) and post.get("title") and post.get("caption")
            and isinstance(post.get("slides"), list) and len(post["slides"]) >= 2
            and all(isinstance(x, dict) and x.get("headline") for x in post["slides"]))


def _normalize(data, key: str) -> dict | None:
    """Bringt abweichende Tool-Antworten in die Form {key: [...]}.
    Beobachtet bzw. abgesichert: Liste als JSON-Text, anderer Feldname, Einzelobjekt, Liste direkt."""
    if isinstance(data, str):
        try:
            data = json.loads(data)
        except json.JSONDecodeError:
            return None
    if isinstance(data, list):
        return {key: data}
    if not isinstance(data, dict):
        return None
    value = data.get(key)
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except json.JSONDecodeError:
            value = None
    if isinstance(value, list):
        return {key: value}
    if key == "posts" and isinstance(data.get("slides"), list):
        return {key: [data]}  # ein einzelner Post statt Liste
    lists = [v for v in data.values() if isinstance(v, list)]
    if len(lists) == 1:
        return {key: lists[0]}
    return None


def _extract_json(text: str, key: str) -> dict | None:
    """Fallback: JSON-Objekt aus einer Textantwort holen."""
    text = re.sub(r"```(?:json)?", "", text)
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end <= start:
        return None
    try:
        data = json.loads(text[start:end + 1])
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, dict) and key in data else None


def web_search_tool(cfg: dict) -> dict:
    ws = cfg.get("web_search", {})
    return {
        "type": "web_search_20250305",
        "name": "web_search",
        "max_uses": ws.get("max_uses", 6),
        "user_location": {"type": "approximate", "country": "AT",
                          "timezone": cfg.get("posting", {}).get("timezone", "Europe/Vienna")},
    }


def call_claude(cfg: dict, system: str, user: str, tool: dict, temperature: float = 1.0,
                search: bool = False) -> dict:
    """Ruft Claude auf und liefert das Ergebnis des Tools als dict.

    Neuere Modelle erlauben teils kein erzwungenes Tool (tool_choice „tool“/„any“) und keine
    eigene Temperatur. Deshalb wird das Tool nur angeboten und klar angewiesen; nicht
    unterstützte Parameter werden bei einer Fehlermeldung automatisch weggelassen.
    Mit search=True darf Claude vorher im Web recherchieren (Server-Tool web_search).
    """
    key = require_env("ANTHROPIC_API_KEY")
    result_key = next(iter(tool["input_schema"]["required"]))
    headers = {"x-api-key": key, "anthropic-version": "2023-06-01", "content-type": "application/json"}
    if os.environ.get("ANTHROPIC_WORKSPACE_ID"):
        headers["anthropic-workspace-id"] = os.environ["ANTHROPIC_WORKSPACE_ID"]
    tools = [tool] + ([web_search_tool(cfg)] if search else [])
    hint = (" Recherchiere vorher mit web_search, wo nötig." if search else "")
    messages: list[dict] = [{"role": "user", "content": user}]
    body = {
        "model": cfg["model"],
        "max_tokens": cfg.get("max_tokens", 32000),
        "temperature": temperature,
        "system": system + f"\n\nAUSGABE:{hint} Antworte am Ende ausschließlich, indem du das Tool "
                           f"{tool['name']} genau einmal aufrufst. Kein Text danach.",
        "messages": messages,
        "tools": tools,
        "tool_choice": {"type": "auto"},
    }
    if cfg.get("effort"):
        body["output_config"] = {"effort": cfg["effort"]}

    searches = 0
    for _ in range(8):  # Wiederholungen für Parameter-Fallbacks und pause_turn
        r = requests.post(API_URL, json=body, timeout=900, headers=headers)
        if r.status_code == 400:
            dropped = next((p for p in ("temperature", "tool_choice", "output_config")
                            if p in body and p in r.text), None)
            if dropped:
                print(f"Hinweis: Parameter „{dropped}“ wird vom Modell nicht akzeptiert – weggelassen.", flush=True)
                body.pop(dropped)
                continue
            if search and "web search" in r.text.lower():
                raise SystemExit("Websuche ist für diese Organisation in der Claude Console deaktiviert. "
                                 "Dort aktivieren oder in config.yaml web_search.enabled: false setzen.")
        if r.status_code != 200:
            raise SystemExit(f"Claude-API-Fehler {r.status_code}: {r.text[:500]}")
        data_all = r.json()
        searches += sum(1 for b in data_all.get("content", []) if b.get("type") == "server_tool_use")
        if data_all.get("stop_reason") == "pause_turn":
            # lange Suchrunde pausiert: Antwort unverändert zurückschicken, dann läuft sie weiter
            messages.append({"role": "assistant", "content": data_all["content"]})
            continue
        break
    else:
        raise UnusableError("Zu viele Wiederholungen (pause_turn/Fallbacks)")
    if searches:
        print(f"  ↳ {searches} Websuche(n)", flush=True)
    content = data_all.get("content", [])
    if data_all.get("stop_reason") == "max_tokens":
        raise TruncatedError("Antwort wurde abgeschnitten")
    for block in content:
        if block.get("type") == "tool_use" and block.get("name") == tool["name"]:
            normalized = _normalize(block.get("input"), result_key)
            if normalized is not None:
                return normalized
    text = "".join(b.get("text", "") for b in content if b.get("type") == "text")
    data = _normalize(_extract_json(text, result_key), result_key) if text else None
    if data:
        return data
    blocks = [b.get("type") for b in content]
    raise UnusableError(f"Kein verwertbares Ergebnis (stop_reason={data_all.get('stop_reason')}, Blöcke={blocks}). "
                        f"Antwortanfang: {text[:300] or str(content)[:300]}")


def pick_pillars(cfg: dict, count: int) -> list[dict]:
    """Gewichtete Auswahl der Säulen, optional angepasst an die Insights."""
    pillars = cfg["content"]["pillars"]
    factors = load_json(STATE_FILE, {}).get("pillar_factor", {}) if cfg["content"].get("adapt_weights") else {}
    weights = [p["weight"] * factors.get(p["id"], 1.0) for p in pillars]
    # Säulen nach Gewicht sicher einplanen, Rest gewichtet zufällig
    chosen = [p for p, _ in sorted(zip(pillars, weights), key=lambda x: -x[1])][:min(count, len(pillars))]
    while len(chosen) < count:
        chosen.append(random.choices(pillars, weights=weights, k=1)[0])
    random.shuffle(chosen)
    return chosen


def recent_titles(limit: int = 60) -> list[str]:
    titles = [h.get("title", "") for h in load_json(HISTORY_FILE, [])][-limit:]
    for item in queue_items():
        titles.append(json.loads((item / "post.json").read_text(encoding="utf-8")).get("title", ""))
    return [t for t in titles if t]


def select_ideas(ideas: list[dict], plan: list[dict]) -> list[dict]:
    """Pro geplanter Säule die beste Idee; gleiche Formate werden abgewertet."""
    pool = list(ideas)
    used_formats: Counter = Counter()
    selected = []
    for p in plan:
        cands = [i for i in pool if i["pillar"] == p["id"]] or pool
        if not cands:
            break
        best = max(cands, key=lambda i: i["originality"] * 1.3 + i["usefulness"] - used_formats[i["format"]] * 3)
        selected.append(best)
        used_formats[best["format"]] += 1
        pool.remove(best)
    return selected


def lint(post: dict, cfg: dict) -> list[str]:
    """Findet verbotene Floskeln und durchgerutschte Format-/Säulennamen."""
    text = " ".join([post["caption"]] + [" ".join(s.values()) for s in post["slides"]]).replace("*", "")
    notes = [f"Floskel „{p}“ gefunden" for p in cfg["content"].get("banned_phrases", [])
             if re.search(re.escape(p), text, re.I)]
    # Säulennamen wie „Prompt“ oder „Skill“ sind normale Wörter – geprüft werden nur Formatnamen und „Tool-Check“
    labels = ["Tool-Check"] + [f["name"].replace(" …", "") for f in cfg["content"].get("formats", [])]
    notes += [f"Interner Name „{n}“ steht im Text" for n in labels
              if len(n) > 5 and re.search(re.escape(n), text, re.I)]
    long = [i + 1 for i, s in enumerate(post["slides"]) if len(s.get("body", "").split()) > 32]
    if long:
        notes.append("Lange Texte auf Slide " + ", ".join(map(str, long)))
    return notes


def clean_post(post: dict, cfg: dict) -> dict:
    c = cfg["content"]
    post["slides"] = [{k: v.strip() for k, v in s.items() if isinstance(v, str) and v.strip()}
                      for s in post["slides"]][: c["slides_max"]]
    post["hashtags"] = [t.strip().lstrip("#").replace(" ", "") for t in post.get("hashtags", []) if t.strip()][: c["hashtags_max"]]
    caption = post["caption"].strip()
    if c.get("ai_disclosure"):
        caption += f"\n\n{c['ai_disclosure']}"
    if post["hashtags"]:
        caption += "\n\n" + " ".join(f"#{t}" for t in post["hashtags"])
    post["caption_final"] = caption[:2200]
    notes = [n for n in [post.get("review_notes", "").strip()] + lint(post, cfg) if n]
    post["review_notes"] = " · ".join(notes)
    return post


def generate(cfg: dict, count: int) -> tuple[list[dict], list[dict]]:
    c = cfg["content"]
    plan = pick_pillars(cfg, count)
    n_ideas = count * c.get("ideas_per_post", 4)
    pillars_txt = "\n".join(f"- {p['id']} – {p['name']}: {p['description']}" for p in c["pillars"])
    formats_txt = "\n".join(f"- {f['id']} – {f['name']}: {f['description']}" for f in c["formats"])
    need = Counter(p["id"] for p in plan)
    need_txt = ", ".join(f"{k}: mind. {v * c.get('ideas_per_post', 4)}" for k, v in need.items())
    system = base_system(cfg)

    # Stufe 1 – Ideen
    ideas = call_claude(cfg, system, f"""Sammle {n_ideas} Post-Ideen. Verteilung nach Säulen: {need_txt}.

SÄULEN:
{pillars_txt}

FORMATE (frei kombinierbar mit jeder Säule, „logbuch“ nur für making_of):
{formats_txt}

Regeln für die Ideen-Runde:
- Kombiniere Säule und Format bewusst ungewöhnlich. Nutze möglichst viele verschiedene Formate.
- Die ersten Ideen, die dir einfallen, sind meist die, die alle haben. Verwirf sie und geh weiter.
- Bewerte dich ehrlich: originality 9–10 nur, wenn du so etwas wirklich noch nie gesehen hast.

{context_block(cfg)}

Gib die Ideen über das Tool submit_ideas zurück.""", ideas_tool(cfg), temperature=1.0)["ideas"]

    chosen = select_ideas(ideas, plan)
    print(f"Ideen-Runde: {len(ideas)} Ideen, {len(chosen)} ausgewählt")
    for i in sorted(ideas, key=lambda x: -(x["originality"] * 1.3 + x["usefulness"])):
        mark = "★" if i in chosen else " "
        print(f" {mark} O{i['originality']:>2} N{i['usefulness']:>2} [{i['pillar']}/{i['format']}] {i['title']} – {i['twist']}")
    TMP.mkdir(exist_ok=True)
    (TMP / "ideas.json").write_text(json.dumps({"all": ideas, "chosen": chosen}, ensure_ascii=False, indent=2), encoding="utf-8")

    # Stufe 2 – Ausschreiben, in kleinen Paketen (lange Antworten werden sonst abgeschnitten)
    rules = FORMAT_RULES.format(smin=c['slides_min'], smax=c['slides_max'], hmax=c['hashtags_max'])
    ctx = context_block(cfg)

    ws = cfg.get("web_search", {})
    search_pillars = set(ws.get("pillars", [])) if ws.get("enabled") else set()

    def write(batch: list[dict]) -> list[dict]:
        brief = "\n".join(f"{i + 1}. [{x['pillar']} / {x['format']}] {x['title']} – Dreh: {x['twist']}"
                          for i, x in enumerate(batch))
        search = any(x["pillar"] in search_pillars for x in batch)
        research = f"""
RECHERCHE (Websuche ist verfügbar, heute ist der {now(cfg).strftime('%d.%m.%Y')}):
- Prüfe für jeden Post mit konkreten Tools, Funktionen, Modellen oder Preisen per web_search, ob das aktuell
  so stimmt und so heißt. Bevorzuge offizielle Seiten und Doku der Anbieter, keine SEO-Listen.
- Verwende nur bestätigte Details. Was du nicht bestätigen kannst: weglassen oder allgemeiner formulieren.
- Beruht der Dreh einer Idee auf einer falschen Annahme, pass ihn an und vermerke das in review_notes.
- Schreib die wichtigsten Quellen-URLs in review_notes (Format „Quelle: <url>“).
""" if search else ""
        result = call_claude(cfg, system, f"""Schreib diese {len(batch)} Ideen als fertige Karussells aus, in dieser Reihenfolge:
{brief}

{rules}
{research}
Halte den Dreh jeder Idee durch – nicht beim Ausschreiben in Standard-Formulierungen zurückfallen.
Jede Slide muss für sich einen Grund liefern, weiterzuwischen.

{ctx}

Gib die Posts über das Tool submit_posts zurück.""", posts_tool(cfg), temperature=0.8, search=search)
        return result.get("posts", [])

    posts: list[dict] = []
    for start in range(0, len(chosen), 2):
        batch = chosen[start:start + 2]
        try:
            got = write(batch)
        except (TruncatedError, UnusableError) as e:
            print(f"Paket nicht verwertbar ({e}) – schreibe die Posts einzeln.", flush=True)
            got = []
            for idea in batch:
                try:
                    got += write([idea])
                except (TruncatedError, UnusableError) as e2:
                    print(f"WARNUNG: „{idea['title']}“ übersprungen: {e2}", flush=True)
        for post in got:
            if valid_post(post):
                posts.append(post)
            else:
                print(f"WARNUNG: unvollständiger Post übersprungen: {str(post)[:120]}", flush=True)
        print(f"✓ {len(posts)}/{len(chosen)} Posts ausgeschrieben", flush=True)
    if not posts:
        raise SystemExit("Keine verwertbaren Posts erhalten.")

    # Stufe 3 – Kritik-Runde: jeder Post wird gegen alle Regeln geprüft und gezielt überarbeitet
    if cfg.get("review", {}).get("enabled"):
        posts = [review_post(cfg, system, rules, ctx, p) for p in posts]
    return posts, chosen


REVIEW_CHECKLIST = """PRÜFLISTE – geh jeden Punkt durch:
1. Hook: Erzeugt Slide 1 eine offene Frage, die erst die folgenden Slides beantworten? Würde ein Vielnutzer
   von KI-Content beim Wischen hängen bleiben? Wenn nicht: schärfer, konkreter, überraschender.
2. Einheitsbrei: Klingt irgendeine Slide wie ein Standard-KI-Karussell? Dann umschreiben, mit dem Dreh der Idee.
3. Sprachstil: kurze Sätze, Verben statt Hauptwörter, keine Labels vor Headlines, keine internen Säulen- oder
   Formatnamen, keine Füllwörter, Wortgrenzen (Headline ca. 7, Cover ca. 10, body ca. 25, box ca. 50 Wörter).
4. Fakten: Keine erfundenen Zahlen, Erlebnisse oder Ergebnisse (Erlebnisse der Page nur laut Journal/Stats).
   Tool-Details ohne Quelle in review_notes: entfernen oder allgemeiner formulieren.
5. Nutzen: Ist der Post sofort nachmachbar? Ist ein Prompt oder Skill in der box vollständig und funktioniert
   er so, wie er dasteht? Löst der Inhalt ein, was der Hook verspricht?
6. Rote Linie: Jede Slide liefert einen Grund weiterzuwischen, keine Wiederholungen, keine Lückenfüller.
7. Caption: bringt einen Zusatz-Gedanken, endet mit einer konkreten Frage, keine Hashtags.
8. *Sternchen*: 1–2 Schlüsselwörter pro Slide, nie ganze Sätze."""


def review_post(cfg: dict, system: str, rules: str, ctx: str, post: dict) -> dict:
    """Zweiter Durchgang als strenger Redakteur. Bei Fehlern bleibt der Originalpost erhalten."""
    try:
        found = lint(post, cfg)
    except (AttributeError, TypeError):
        found = []
    found_txt = ("\nDIE AUTOMATISCHE PRÜFUNG HAT GEFUNDEN – unbedingt beheben:\n"
                 + "\n".join(f"- {n}" for n in found) + "\n") if found else ""
    original = json.dumps(post, ensure_ascii=False, indent=2)
    try:
        result = call_claude(cfg, system, f"""Du bist jetzt der strengste Redakteur der Page. Unten steht ein fertiger
Karussell-Post. Prüf ihn und gib die verbesserte Fassung zurück.

{REVIEW_CHECKLIST}
{found_txt}
REGELN FÜR DIE ÜBERARBEITUNG:
- Ändere nur, was den Post wirklich besser macht. Gute Stellen bleiben wörtlich stehen.
- Behalte pillar, format, title und den Dreh. Kein neues Thema, nicht glattbügeln, nicht braver machen.
- review_notes: übernimm die bestehenden Hinweise und Quellen und ergänze nur, was ein Mensch vor dem Posten
  noch prüfen muss. Keine Liste deiner Änderungen.

{rules}

<post>
{original}
</post>

{ctx}

Gib genau einen Post über das Tool submit_posts zurück.""", posts_tool(cfg), temperature=0.5)
        revised = result.get("posts", [])
    except (TruncatedError, UnusableError) as e:
        print(f"WARNUNG: Kritik-Runde für „{post['title']}“ fehlgeschlagen ({e}) – Original bleibt.", flush=True)
        return post
    if revised and valid_post(revised[0]):
        new = revised[0]
        old_notes, new_notes = post.get("review_notes", "").strip(), new.get("review_notes", "").strip()
        lost = [u for u in re.findall(r"https?://\S+", old_notes) if u not in new_notes]
        if lost:  # Quellen aus der Recherche dürfen nicht verloren gehen
            new["review_notes"] = " · ".join(x for x in [new_notes, "Quellen: " + " ".join(lost)] if x)
        print(f"✓ Kritik-Runde: {post['title']}", flush=True)
        return new
    print(f"WARNUNG: Kritik-Runde für „{post['title']}“ unbrauchbar – Original bleibt.", flush=True)
    return post


def write_pr_body(dirs: list[Path]) -> None:
    repo = os.environ.get("GITHUB_REPOSITORY", "")
    branch = os.environ.get("PR_BRANCH", "")
    lines = [f"## {len(dirs)} neue Posts zur Freigabe", "",
             "**Merge = alle freigeben.** Einzelne Posts rauswerfen: unter *Files changed* den Ordner löschen "
             "oder nach dem Merge den Ordner in `queue/` löschen, bevor er dran ist.", ""]
    for d in dirs:
        post = json.loads((d / "post.json").read_text(encoding="utf-8"))
        lines += [f"### {post['title']}", f"`{post['pillar']}` · `{post.get('format', '')}` · `{d.name}`", ""]
        if repo and branch:
            lines += [" ".join(f'<img src="https://raw.githubusercontent.com/{repo}/{branch}/queue/{d.name}/{img}" width="160">'
                               for img in post["images"]), ""]
        if post.get("reel") and repo and branch:
            lines += [f"▶ [Reel ansehen ({post['reel']['seconds']} s)](https://github.com/{repo}/blob/{branch}/queue/{d.name}/{post['reel']['file']})", ""]
        if post.get("review_notes"):
            lines += [f"> ⚠️ **Bitte prüfen:** {post['review_notes']}", ""]
        lines += ["<details><summary>Caption</summary>", "", post["caption_final"], "", "</details>", ""]
    TMP.mkdir(exist_ok=True)
    (TMP / "pr_body.md").write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    import sys
    sys.stdout.reconfigure(line_buffering=True)
    ap = argparse.ArgumentParser()
    ap.add_argument("--count", default="", help="Anzahl Posts (Standard aus config.yaml)")
    ap.add_argument("--from-json", type=Path, help="Posts aus Datei statt von Claude (zum Testen)")
    args = ap.parse_args()

    cfg = load_config()
    count = int(args.count) if str(args.count).strip() else cfg["content"]["posts_per_batch"]
    if args.from_json:
        posts = json.loads(args.from_json.read_text(encoding="utf-8"))
    else:
        posts, _ = generate(cfg, count)

    stamp = now(cfg).strftime("%Y-%m-%d-%H%M")
    QUEUE.mkdir(exist_ok=True)
    dirs = []
    for i, post in enumerate(posts, start=1):
        post = clean_post(post, cfg)
        d = QUEUE / f"{stamp}-{i:02d}-{slugify(post['title'])}"
        d.mkdir(parents=True, exist_ok=True)
        (d / "post.json").write_text(json.dumps(post, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        render_post(d, cfg)
        dirs.append(d)
        print(f"✓ {d.name}")
    write_pr_body(dirs)


if __name__ == "__main__":
    main()
