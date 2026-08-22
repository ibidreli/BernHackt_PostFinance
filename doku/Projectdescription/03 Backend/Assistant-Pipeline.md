---
tags: [backend, ai, algorithmus]
status: in-arbeit
branch: origin/feature/prognosis, origin/5-feature-future-me-chatbot-szenario-assistent
---

# Assistant-Pipeline

Code (auf Branch `origin/feature/prognosis`): `app/services/assistant_service.py` (~480 Zeilen), `app/services/intent_service.py`, `app/schemas/assistant.py`, `tests/test_assistant.py` · Prompts: `prompts/assistant_extraction.md`, `prompts/assistant_phrasing.md` · Feature: [[Future-Me Chatbot]]

## Die sechs Schritte

```
Nutzerfrage
  → LLM-Extraktion        (Structured Outputs: Intent, Betrag, Horizont, Kategorie)
  → Validierung           (Parameter plausibel? sonst Rückfrage mit Button-Optionen)
  → forecast_service      (deterministische Berechnung — siehe unten)
  → Antwortlogik          (yes / tight / no_unless + Hebel)
  → LLM-Formulierung      (Text aus den fertigen Zahlen)
  → Chart-Auswahl         (einer von drei festen Typen)
```

Das Modell wird **zweimal** aufgerufen und sieht nie eine Rohtransaktion: beim ersten Mal nur die Frage, beim zweiten Mal nur das fertige Ergebnisobjekt. **`_verify_numbers` erzwingt**, dass keine Zahl in der Antwort vom LLM stammt — jeder Betrag im Text wird gegen `facts` geprüft.

## Rechnen: [[Forecast-Service]] + Extrapolation

Für `present`/`1y` wird direkt die Prognose benutzt. Für `5y`/`10y` wird die 365d-Prognose vorwärts extrapoliert — mit den sichtbaren Annahmen Lohnwachstum (Default 1.0 % p.a.) und Inflation auf variable Ausgaben (1.5 % p.a.), Defaults in `core/config.py` (`SALARY_GROWTH_DEFAULT_PCT`, `INFLATION_DEFAULT_PCT`, `TIGHT_BUFFER_MONTHS=3`). Bei `horizon=present` sind beide Annahmen per Definition 0. Keine Zins-/Renditeannahme.

Antwortlogik-Bausteine: `gap_chf` (Ziel − Prognose), `required_monthly_chf` (Lücke / Restmonate), `levers` (die 3 teuersten **variablen** Kategorien; `potential_chf` = Differenz zum historischen Monats-Minimum der Kategorie — ehrlicher als die pauschalen 50 % aus dem Issue), `wait_months` bei `tight`.

## `intent_service.py`

Regelbasierte Regex-Extraktion von Intent/Betrag/Horizont/Kategorie inkl. Schweizer Zahlformaten — Basis des `cached`-Modus und Validierungs-Fallback.

## OpenAI-Anbindung (Branch `origin/5-…`)

`openai==1.109.1` (bewusst 1.x gepinnt — Code ist gegen die 1.x-Structured-Outputs-API geschrieben), Konfiguration über `apps/api/app/.env` ([[Setup & Betrieb]]). **Fail-fast:** `ASSISTANT_MODE=live` ohne `OPENAI_API_KEY` lässt den Container beim Start mit klarer `RuntimeError` sterben statt später mitten im Chat.

## Team-abgestimmte Abweichungen vom Issue

1. **Timeout (8 s) → explizite Fehlermeldung**, kein stiller Template-Fallback, der aussieht wie eine geprüfte Antwort.
2. **"Kantine halbieren"-`what_if` nicht abbildbar** (konsistent mit [[Forecast-Service]]) → `unsupported` oder Rückfrage, keine erfundene Rechnung.
3. **Folgefragen im Scope:** In-Memory-State pro `conversation_id`.
4. **`potential_chf` = historisches Minimum** statt pauschal 50 %.

## Tests

`tests/test_assistant.py` (~190 Zeilen) — die einzige automatisierte Testdatei des Projekts: Zustandslogik an den Schwellwerten, Hebel-Auswahl, Zahlenabgleich.
