---
tags: [feature, ai]
status: umgesetzt
issue: 5
branch: main
---

# Future-Me Chatbot (Szenario-Assistent)

Spec: [[Issue 5 – Future-Me Chatbot]] · Backend: [[Assistant-Pipeline]] · UI: [[Assistant-Seite]] · rechnet mit dem [[Forecast-Service]]

## Die Idee

Nutzer:innen fragen in natürlicher Sprache — *"Kann ich mir in 5 Jahren ein Auto für CHF 30'000 leisten?"* — und bekommen eine belastbare, begründete Antwort mit passender Grafik. Nie nur ja/nein, sondern Betrag, Bedingung und den wirksamsten Hebel.

**Das zentrale Architekturprinzip:** *"Das Sprachmodell versteht die Frage und formuliert die Antwort. Gerechnet wird deterministisch, mit derselben Funktion wie der Slider. Ein Sprachmodell darf bei Geld nicht rechnen."* Das LLM sieht nie eine Rohtransaktion und produziert keine Zahlen — ein automatischer Zahlenabgleich prüft das nach jeder Formulierung.

## Bewusst eng gehaltener Scope

- **Genau drei Fragetypen:** `affordability`, `what_if`, `time_to_goal`. Alles andere → `unsupported` mit Nennung der drei Möglichkeiten.
- **Vier Horizonte:** `present` (einzige Stufe ganz ohne Annahmen), `1y`, `5y`, `10y` — mit sichtbaren, per Regler veränderbaren Annahmen (Lohnwachstum, Inflation, Sparquote). Kein Orakel, ein Szenariorechner. Keine Zins-/Renditeannahme.
- **Dreistufige Antwort:** `yes` / `tight` (Puffer < 3 Monatsausgaben) / `no_unless` — Letzteres ist die eigentliche Leistung: Fehlbetrag + nötiger Mehrbetrag + wirksamster Hebel aus **variablen** Kategorien.
- **Maximal eine Rückfrage**, immer mit Button-Optionen. **Drei feste Chart-Typen** — das Modell wählt, generiert nicht.
- **Ton:** nüchtern, keine Ich-Form der Zukunftsperson, keine Emojis. Prompts versioniert unter `apps/api/app/prompts/`.

## Offline-Fallback für die Live-Demo

`ASSISTANT_MODE=cached` beantwortet vorbereitete Demo-Fragen ohne jeden externen API-Call — der [[Forecast-Service]] rechnet dabei **trotzdem echt**, nur die Formulierung kommt aus einem Template. Es wird nichts vorgetäuscht. Neu seit dem 22.08. dabei: *"Was wäre, wenn ich Gastronomie halbiere?"* (läuft ohne Key und ist als Vorschlags-Chip im `present`-Horizont gelistet).

## Status

**Backend fertig und auf `main` gemergt** (PR #12), live gegen die echte OpenAI-API und die echten Sample-Daten getestet (`apps/api/STATUS_FEATURE_NR_5_BACKEND.md`). Endpunkte: `POST /api/v1/assistant/ask`, `GET /api/v1/assistant/suggestions` (REST, nicht OData — folgt dem Issue-Contract wörtlich; Referenz: `apps/api/ASSISTANT_API.md`).

Es gab zwischenzeitlich eine zweite, unabhängige Chatbot-Implementierung auf `origin/feature/prognosis` (regelbasiert statt LLM, dort selbst als Platzhalter markiert). Beim Merge mit `main` wurde entschieden, die hier beschriebene (vollständig getestete, LLM-integrierte) Implementierung zu behalten. Deren Testdatei `tests/test_assistant.py` wurde dabei mit entfernt — inzwischen ist der `cached`-Pfad wieder automatisiert getestet (`tests/test_assistant_cached.py`, läuft ohne Key; siehe [[Projektstatus]]).

Das Frontend ([[Assistant-Seite]]) wurde am 22.08.2026 auf die neuen Endpunkte und das neue Response-Schema umgestellt (diskriminierte Chart-Typen, `suggestions`-Feld, Fehleranzeige für 502/504, `conversation_id` für Folgefragen) und liegt jetzt auf **`/future-me`** (Label "Future Me").

## Ausbau vom 22.08. ([[Sollstatus]]-Verbindungen)

- **`what_if` versteht Kategorie-Prozent-Fragen:** `ExtractedIntent` hat neu `category_hint` + `percent`; `category_percent_hint`-Fragen sind nicht mehr `unsupported`, sondern lösen zu einem `adjust_category`-Eingriff auf (Subkategorie-Match gewinnt über Hauptkategorie; "halbieren" heisst default −50). Der Intent-Extraktions-Prompt wurde entsprechend erweitert.
- **`intervention` in `what_if`-Antworten:** maschinenlesbares Feld mit dem aufgelösten Adjustment — Grundlage für **"Als Szenario in Prognose übernehmen"** (wird zum Chip auf `/`).
- **Hebel verlinken auf ihre Kategorie-Blase** in `/kategorien`; **vorbefüllte Fragen** aus Prognose/Explorer landen im Eingabefeld (nicht automatisch abgeschickt), Übergabe via `core/handoff.ts` bzw. teilbarem `/future-me?q=…`.
