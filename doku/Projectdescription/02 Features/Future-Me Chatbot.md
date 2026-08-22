---
tags: [feature, ai]
status: backend-fertig
issue: 5
branch: 5-feature-future-me-chatbot-szenario-assistent
---

# Future-Me Chatbot (Szenario-Assistent)

Spec: [[Issue 5 – Future-Me Chatbot]] · Backend: [[Assistant-Pipeline]] · UI: [[Assistant-Seite]] (inkompatibel, siehe Status unten) · rechnet mit dem [[Forecast-Service]]

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

`ASSISTANT_MODE=cached` beantwortet 5 vorbereitete Demo-Fragen ohne jeden externen API-Call — der [[Forecast-Service]] rechnet dabei **trotzdem echt**, nur die Formulierung kommt aus einem Template. Es wird nichts vorgetäuscht.

## Status

**Backend fertig** auf Branch `5-feature-future-me-chatbot-szenario-assistent`, live gegen die echte OpenAI-API und die echten Sample-Daten getestet (`apps/api/STATUS_FEATURE_NR_5_BACKEND.md`). Endpunkte: `POST /api/v1/assistant/ask`, `GET /api/v1/assistant/suggestions`.

Es gab zwischenzeitlich eine zweite, unabhängige Chatbot-Implementierung auf `origin/feature/prognosis` (regelbasiert statt LLM, dort selbst als Platzhalter markiert). Beim Merge mit `main` wurde entschieden, die hier beschriebene (vollständig getestete, LLM-integrierte) Implementierung zu behalten.

**Offener Punkt:** Das bestehende Frontend ([[Assistant-Seite]]) ruft die Endpunkte der verworfenen Implementierung (`/api/v1/Ask`) auf, nicht die hier aktiven (`/api/v1/assistant/ask`) — muss vor dem Pitch angepasst werden.
