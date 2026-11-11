# Journal

Hier schreibst du kurz rein, was beim Aufbau der Page passiert – Stichworte reichen.
Das ist die **einzige Quelle**, aus der die KI Erlebnisse und Zahlen für Making-of-Posts nimmt.
Alles andere formuliert sie als Anleitung, nicht als „ich habe …“. Neueste Einträge unten.

**Meilensteine:** Wenn du etwas am Setup änderst (neues Format, Reels, Bio geändert, Kooperation …),
schreib eine Zeile `- Meilenstein: …` unter das Datum. Das Dashboard vergleicht dann automatisch
14 Tage davor mit 14 Tagen danach. Änderungen an `config.yaml` werden ohnehin automatisch erfasst.

## 10.11.2026
- Idee: eine Instagram-Page, die sich mit KI selbst betreibt – und genau das zeigt.
- Entscheidung: keine Finanztipps, sondern zeigen, wie KI für einen arbeitet (Tools, Prompts, Skills).
- Entscheidung: zuerst auf Deutsch, Englisch später als eigene zweite Page.
- Name gewählt: Kollege KI (@kollege.ki). Die KI ist der Kollege, der die Arbeit übernimmt.
- Pipeline gebaut: Claude sammelt pro Post 4 Ideen und schreibt nur die beste aus, ein Python-Script gestaltet die Slides,
  GitHub Actions postet. Ich gebe jede Woche alles am Handy per Pull Request frei.
- Die Page testet selbst, welche Uhrzeit am besten funktioniert (07:30, 12:15, 18:30 im Wechsel).
- Meilenstein: Start – Pipeline mit Kreativ-Stufe (4 Ideen pro Post) live
- Stand: 0 Follower, 0 Posts.

## 11.11.2026
- Logo fertig: ein „K“ und daneben ein grüner Cursor statt dem „I“ – die KI, die gerade für dich tippt.
  Mehrere Varianten verworfen (Textcursor mit Querstrichen, Sprechblase, Eingabefeld, Schriftzug „Kollege“), am Ende blieb der erste, einfachste Entwurf.
- Hürde: GitHub nimmt bei neuen Accounts derzeit keine Outlook- oder Hotmail-Adressen an – Lösung war eine Gmail-Adresse.
- Hürde: Meta gibt neuen Apps nur noch „Unified Login“. Der Token sah anders aus als erwartet, die Pipeline musste angepasst werden.
- Hürde: Der erste Content-Lauf scheiterte mehrmals (Claude-Key ohne Workspace, nicht unterstütztes Tool-Format, zu lange Antworten).
  Jetzt schreibt Claude die Posts in Zweier-Paketen.
- Die ersten Posts im alten Design verworfen: Formulierungen zu steif, Schriftgrößen uneinheitlich.
- Meilenstein: Neues Slide-Format „Editor-Fenster“ – jede Slide sieht aus wie ein Fenster, in dem die KI tippt.
  Schrift Bricolage Grotesque, Rahmenfarbe je Serie (Prompt grün, Tool-Check und Workflow hell, Skill schwarz).
- Meilenstein: Erster Post live (von Hand ausgelöst, ab morgen postet die Page selbst).
- Nach gut 2 Stunden: 0 Aufrufe – ein neues Konto ohne Follower hat niemanden, dem Instagram den Post zuerst zeigt.
- Meilenstein: Automatische Reels – aus jedem Karussell entsteht ein Video, in dem die KI die Headline tippt (nur im Reels-Bereich, das Profil-Raster bleibt Karussells).
- Stand: 0 Follower, 1 Post.
