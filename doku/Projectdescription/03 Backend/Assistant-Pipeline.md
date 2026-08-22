---
tags: [backend, ai, algorithmus]
status: fertig
branch: 5-feature-future-me-chatbot-szenario-assistent
---

# Assistant-Pipeline

Code: `app/services/assistant_service.py`, `intent_service.py`, `answer_service.py`, `chart_service.py`, `formulation_service.py`, `verification_service.py`, `cache_service.py`, `llm_client.py` · Schemas: `app/schemas/assistant.py` · Prompts: `app/prompts/intent_extraction_v1.md`, `answer_formulation_v1.md` · Feature: [[Future-Me Chatbot]] · Details/Bugs: `apps/api/STATUS_FEATURE_NR_5_BACKEND.md`

## Die sechs Schritte

```
Nutzerfrage
  → LLM-Extraktion        (OpenAI Structured Outputs: Intent, Betrag, Horizont, Kategorie)
  → Validierung            (Parameter plausibel? sonst Rückfrage mit Button-Optionen)
  → forecast_service       (deterministische Berechnung — siehe unten)
  → Antwortlogik           (yes / tight / no_unless + Hebel)
  → LLM-Formulierung       (Text aus den fertigen Zahlen)
  → Chart-Auswahl          (einer von drei festen Typen)
```

Das Modell wird **zweimal echt aufgerufen** (`gpt-4o-mini`, `openai==1.109.1`) und sieht nie eine Rohtransaktion: beim ersten Mal nur die Frage, beim zweiten Mal nur das fertige Ergebnisobjekt. `verification_service.verify_answer_text` prüft danach jede CHF-/Monats-Zahl im Antworttext typgebunden gegen `facts`/`levers`; bei Abweichung greift automatisch dieselbe Template-Formulierung wie im Cache-Modus.

## Rechnen: [[Forecast-Service]] + `project_long_term`

`present` nutzt direkt `forecast(horizon=next_salary)`. `1y`/`5y`/`10y` laufen über `project_long_term()`: jede RecurringPayment wird zu einer monatsäquivalenten Rate (Einzeltermine über 10 Jahre sind nicht sinnvoll auflösbar), Wachstum (Default 1.0 % p.a.) und Inflation (1.5 % p.a.) wirken über stetige monatliche Verzinsung. Bei `horizon=present` sind beide Annahmen per Definition 0. Keine Zins-/Renditeannahme.

Antwortlogik-Bausteine (`answer_service.py`): `gap_chf` (Ziel − Prognose), `required_monthly_chf` (Lücke / Restmonate), `levers` (Top-3 variable Kategorien, `potential_chf` = Differenz zum historischen Monats-Minimum — ehrlicher als die pauschalen 50 % aus dem Issue; "Steuern" explizit ausgeschlossen), `wait_months` bei `tight`.

## `intent_service.py`

Echter OpenAI-Call (Structured Outputs, kein Regex) für Intent/Betrag/Horizont/Kategorie. Rückfrage-Texte kommen aus einer festen Tabelle, nicht vom Modell.

## `ASSISTANT_MODE=cached` (Offline-Fallback)

`cache_service.py`: 5 fest hinterlegte Demo-Fragen, exaktes Text-Matching, **keine** externen API-Calls. `forecast_service` rechnet dabei trotzdem echt — bewiesen, indem der OpenAI-Client im Test aktiv blockiert wird und alle 5 Fragen inkl. Rückfrage-Flow trotzdem durchlaufen.

## Team-abgestimmte Abweichungen vom Issue

1. **Timeout (8s) → explizite Fehlermeldung**, kein stiller Template-Fallback, der aussieht wie eine geprüfte Antwort.
2. **"Kantine halbieren"-`what_if` nicht abbildbar** (konsistent mit [[Forecast-Service]]) → `unsupported` oder Rückfrage, keine erfundene Rechnung.
3. **Folgefragen im Scope:** In-Memory-State pro `conversation_id` (`conversation_state.py`).
4. **`potential_chf` = historisches Minimum** statt pauschal 50 %.

## Tests

Keine automatisierten Tests (bewusste Entscheidung, konsistent mit [[Zukunftsprognose & Simulation]]) — Verifikation über `app/inspect_*.py`-Skripte, live gegen die echte OpenAI-API und die echten Sample-Daten getestet.
