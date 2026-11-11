# Insta-Autopilot

Eine Instagram-Page, die sich mit KI selbst betreibt – und genau das zeigt.

```
Sonntag 18:00   Claude sammelt 28 Ideen → die 7 originellsten werden ausgeschrieben
                → Slides werden gerendert → Pull Request landet auf deinem Handy
Du              10 Min. durchschauen → „Merge" = freigegeben
Täglich         Posten zur passenden Uhrzeit (testet 07:30 / 12:15 / 18:30, lernt die beste)
Täglich früh    Insights holen → beste Uhrzeit, beste Säulen → fließt in die nächste Woche ein
Täglich         Follower-Stand, Meilensteine, Vorher/Nachher-Wirkung → Projektcockpit
Alle 2 Wochen   Instagram-Token automatisch verlängern
```

**Projektcockpit:** `https://<dein-github-name>.github.io/<repo>/` – Ampel, letzter/nächster Post,
offene Freigaben, nächste Schritte, Roadmap, Verlauf und was welcher Schritt gebracht hat.
Am Handy als Lesezeichen auf den Homescreen legen.

**Kosten:** GitHub und Meta-API gratis (öffentliches Repo). Claude-API nach Verbrauch – im
[Anthropic-Dashboard](https://console.anthropic.com) ein Monatslimit setzen.

---

## Einrichtung (einmalig, ca. 45 Min. am Laptop)

### 1. Instagram
Neuen Account anlegen → *Einstellungen → Kontotyp* → **Creator- oder Business-Konto**.

### 2. GitHub-Repo
1. Auf github.com ein **neues öffentliches Repository** anlegen (z. B. `insta-autopilot`).
   Öffentlich, weil Instagram die Bilder von einer öffentlichen URL abholt. Schlüssel bleiben trotzdem geheim (Secrets).
   Passt außerdem zu Build in Public.
2. Inhalt dieses Ordners hochladen (*Add file → Upload files*, inkl. Ordner `.github`).
3. *Settings → Actions → General*:
   - Workflow permissions: **Read and write permissions**
   - Häkchen bei **Allow GitHub Actions to create and approve pull requests**

### 3. Claude-API-Key
[console.anthropic.com](https://console.anthropic.com) → API Keys → neuen Key erstellen.

### 4. Instagram-Zugang (Meta)
1. [developers.facebook.com](https://developers.facebook.com) → *Meine Apps → App erstellen* →
   Anwendungsfall **„Instagram API mit Instagram-Login“** (Instagram API with Instagram Login).
2. In der App unter *Instagram → API-Einrichtung*: deinen Instagram-Account hinzufügen
   (er muss in der App als Tester/Rolle eingetragen sein, dann reicht der Entwicklungsmodus für dein eigenes Konto).
3. Berechtigungen: `instagram_business_basic`, `instagram_business_content_publish`,
   `instagram_business_manage_insights`.
4. **Zugangstoken generieren** (langlebig, 60 Tage) und kopieren.

### 5. GitHub-Token (Token-Verlängerung + Cockpit-Updates)
github.com → *Settings → Developer settings → Fine-grained tokens* → neuer Token
nur für dieses Repo, Berechtigungen **Secrets**, **Contents** und **Pull requests** jeweils *Read and write*.

### 6. Secrets eintragen
Repo → *Settings → Secrets and variables → Actions → New repository secret*:

| Name | Inhalt |
|---|---|
| `ANTHROPIC_API_KEY` | Claude-Key aus Schritt 3 |
| `IG_ACCESS_TOKEN` | Instagram-Token aus Schritt 4 |
| `GH_PAT` | GitHub-Token aus Schritt 5 |
| `IG_USER_ID` | optional – zeigt dir der Workflow „0 · Verbindung testen“ an |

### 7. Anpassen
In `config.yaml` mindestens `brand.name` und `brand.handle` setzen, Farben nach Geschmack,
Etappenziele unter `roadmap`.

### 7b. Cockpit einschalten
Repo → *Settings → Pages* → Source **Deploy from a branch**, Branch `main`, Ordner **/docs** → Save.
Hinweis: Bei einem öffentlichen Repo ist auch das Cockpit öffentlich (passt zu Build in Public,
die Seite ist für Suchmaschinen gesperrt).

### 8. Erster Start
1. *Actions → „0 · Verbindung testen“ → Run workflow* – zeigt Account und Posting-Kontingent.
2. *Actions → „1 · Content generieren“ → Run workflow* – nach ein paar Minuten kommt ein Pull Request.
3. PR in der GitHub-App ansehen → **Merge**.
4. *Actions → „2 · Posten“ → Run workflow* mit `dry_run` = an (Test) – dann mit `force` = an für den ersten echten Post.

Ab dann läuft alles von selbst.

---

## Deine Routine

- **Sonntag/Montag (10 Min.):** PR öffnen, Slides durchwischen, ⚠️-Hinweise prüfen, mergen.
  Einen Post rauswerfen: unter *Files changed* den Ordner löschen, oder nach dem Merge in `queue/`.
- **Laufend:** in `content/journal.md` Stichworte eintragen (Erlebnisse, Zahlen, Fehler).
  Nur von dort nimmt die KI Making-of-Fakten – erfunden wird nichts.
- **Wenn du etwas änderst** (neues Format, Bio, Reels, Kooperation …): im Journal eine Zeile
  `- Meilenstein: …` unter das Datum. Änderungen an `config.yaml` werden automatisch erfasst.
- **Monatlich:** `data/learnings.md` lesen. Wenn die Qualität passt, `posts_per_day` auf 2 erhöhen.

## Tracking & Verkaufsvorlage

Alles wird von Tag 1 an mitgeschrieben, damit du später zeigen und verkaufen kannst, was funktioniert:

| Datei | Inhalt |
|---|---|
| `data/history.json` | jeder Post mit Uhrzeit, Säule, Format, Link |
| `data/insights.csv` | Reichweite, Saves, Shares, Likes, Kommentare pro Post |
| `data/account_daily.csv` | Follower und Beiträge pro Tag |
| `data/milestones.json` | jede Setup-Änderung (automatisch + aus dem Journal) |
| `data/impact.md` | je Meilenstein: 14 Tage vorher vs. nachher (Reichweite, Score, Follower/Tag) |
| `data/learnings.md` | beste Uhrzeiten, Säulen, Formate, Top- und Flop-Posts |

Die gemessenen Zahlen fließen auch in die Making-of-Posts ein – echt statt erfunden.

**Vorlage exportieren:** *Actions → „5 · Vorlage exportieren“* → ZIP unter *Artifacts*.
Enthält Code, Workflows, Formate, Regeln und Roadmap, aber keine Posts, Zahlen, Tokens oder Markendaten.
Optional mit `FALLSTUDIE.md` (deine Meilensteine und ihre Wirkung) als Verkaufsargument.

## Was die Kreativ-Stufe macht

Damit nicht jeder Post nach „5 KI-Tools, die du kennen musst“ klingt:

- **Säulen** (worüber): Tool-Check, Prompt, Skill, Workflow, Making-of
- **Formate** (wie): Schlecht → Gut → Genial, Zweckentfremdet, Die KI als …, Rezept,
  Mythos vs. Realität, Unpopuläre Meinung, Rückwärts, Experiment, Logbuch …
- Claude sammelt **4 Ideen pro Post** und bewertet Originalität und Nutzen,
  der Code wählt die besten mit **möglichst verschiedenen Formaten**.
- **Verbotene Floskeln und Themen** in `config.yaml` – rutscht trotzdem eine durch,
  steht sie als ⚠️ im PR.
- Die Insights fließen zurück: Säulen, die gut laufen, kommen öfter dran.
- Alle Ideen einer Runde liegen im Workflow-Log; eigene Formate einfach in `config.yaml` ergänzen.

## Ordner

```
autopilot/     Code (generate, render, publish, insights, stats, cockpit, export_template, …)
config.yaml    alle Einstellungen
content/       journal.md – dein Logbuch
queue/         freigegebene Posts, die noch kommen
posted/        veröffentlichte Posts inkl. Link
data/          Tracking (siehe oben)
docs/          das Cockpit (index.html)
```

## Workflows

| Workflow | Wann | Was |
|---|---|---|
| 0 · Verbindung testen | manuell | prüft Instagram-Token und Claude-Key |
| 1 · Content generieren | Sonntag 18:00 | Ideen → Posts → Slides → Freigabe-PR |
| 2 · Posten | alle 30 Min. tagsüber | postet, wenn der Slot dran ist |
| 3 · Insights, Statistik & Cockpit | täglich früh | Zahlen holen, auswerten, Cockpit |
| 4 · Token verlängern | 1. und 15. | Instagram-Token erneuern |
| 5 · Vorlage exportieren | manuell | Verkaufsvorlage als ZIP |
| 6 · Cockpit aktualisieren | bei Freigabe, Journal-/Config-Änderung | Cockpit sofort neu |

Einzelnen Post neu rendern (lokal): `python -m autopilot.render queue/<ordner>`

## Grenzen (ehrlich)

- **Uhrzeit:** GitHub startet geplante Läufe teils mit Verzögerung – Posts kommen ±30 Min. um den Slot.
- **Reels** sind noch nicht drin (Phase 2: Text-Reels mit KI-Stimme). Für den Start reichen Karussells –
  sie werden gespeichert und geteilt, und genau das zählt für Reichweite.
- **„Kommentiere SKILL → DM mit Link“** ist noch nicht drin (Phase 2 oder ManyChat).
- **Rechtliches (AT):** Offenlegung nach Mediengesetz in die Bio bzw. auf eine verlinkte Seite,
  Affiliate-Links als Werbung kennzeichnen. Der KI-Hinweis steht automatisch in jeder Caption.
- Meta ändert die API regelmäßig. Wenn etwas bricht: `instagram.api_version` in `config.yaml` anheben.
