---
tags: [feature, ai]
status: in-arbeit
issue: 5
branch: origin/feature/prognosis, origin/5-feature-future-me-chatbot-szenario-assistent
---

# Future-Me Chatbot (Szenario-Assistent)

Spec: [[Issue 5 – Future-Me Chatbot]] · Backend: [[Assistant-Pipeline]] · UI: [[Assistant-Seite]] · rechnet mit dem [[Forecast-Service]]

## Die Idee

Nutzer:innen fragen in natürlicher Sprache — *"Kann ich mir in 5 Jahren ein Auto für CHF 30'000 leisten?"* — und bekommen eine belastbare, begründete Antwort mit passender Grafik. Nie nur ja/nein, sondern Betrag, Bedingung und den wirksamsten Hebel.

**Das zentrale Architekturprinzip** (der Satz für den Code-Walkthrough): *"Das Sprachmodell versteht die Frage und formuliert die Antwort. Gerechnet wird deterministisch, mit derselben Funktion wie der Slider. Ein Sprachmodell darf bei Geld nicht rechnen."* Das LLM sieht nie eine Rohtransaktion und produziert keine Zahlen — `_verify_numbers` prüft das sogar automatisch.

## Bewusst eng gehaltener Scope

- **Genau drei Fragetypen:** `affordability` ("Kann ich mir X leisten?"), `what_if` ("Was wäre wenn …?"), `time_to_goal` ("Wann habe ich X zusammen?"). Alles andere → `unsupported` mit Nennung der drei Möglichkeiten. Drei Fähigkeiten, die immer funktionieren, sind im Pitch mehr wert als ein Bot, der live eine falsche Zahl nennt.
- **Vier Horizonte:** `present` (einzige Stufe ganz ohne Annahmen — Vertrauensanker), `1y`, `5y`, `10y`. Langfrist-Horizonte extrapolieren die 365d-Prognose mit sichtbaren, per Regler veränderbaren Annahmen (Lohnwachstum 1 % p.a., Inflation 1.5 % p.a., Sparquote aus der Historie). Kein Orakel, ein Szenariorechner. Weiterhin keine Zins-/Renditeannahme.
- **Dreistufige Antwort:** `yes` / `tight` (Puffer < 3 Monatsausgaben) / `no_unless` — Letzteres ist die eigentliche Leistung: "Dir fehlen CHF 7'400. Bei CHF 125 mehr pro Monat schaffst du es. Grösster Hebel: Kleidung." Hebel nur aus **variablen** Kategorien ("spar bei der Krankenkasse" ist kein Rat).
- **Maximal eine Rückfrage**, immer mit Button-Optionen (auf dem Beamer tippt niemand). **Drei feste Chart-Typen** (`wealth_over_time`, `goal_progress`, `before_after`) — das Modell wählt, generiert nicht.
- **Ton:** nüchtern, keine Ich-Form der Zukunftsperson, keine Emojis, Beträge über 1 Jahr auf CHF 100 gerundet. Prompts versioniert unter `prompts/` im Repo.

## Offline-Fallback für die Live-Demo

`ASSISTANT_MODE=cached` beantwortet vorbereitete Demo-Fragen ohne externe API-Calls — der [[Forecast-Service]] rechnet dabei **trotzdem echt**, nur die Formulierung kommt aus dem Cache. Es wird nichts vorgetäuscht.

## Status

Auf Branches umgesetzt, nicht auf `main`: die Pipeline und der einzige echte Test des Projekts (`tests/test_assistant.py`) auf `origin/feature/prognosis`, das OpenAI-Setup (openai 1.109, `.env`-Konfiguration, Fail-fast-Start) auf `origin/5-…`. Vier team-abgestimmte Abweichungen vom Issue, u. a.: Timeout → explizite Fehlermeldung statt stillem Template-Fallback; `potential_chf` pro Hebel = Differenz zum historischen Monats-Minimum statt pauschal 50 %; Folgefragen via `conversation_id` sind im Scope. Details: [[Assistant-Pipeline]].
