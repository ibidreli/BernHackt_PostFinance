<!-- Title: Status — Future-Me Chatbot (Backend) -->

# Status: Future-Me Chatbot (Szenario-Assistent) — Backend

Lebendes Dokument analog zu [STATUS_FEATURE_NR_4_BACKEND.md](STATUS_FEATURE_NR_4_BACKEND.md): pro Teilschritt (T0–T13) ein Satz Stand, plus **Bugs**, **Grenzen** und **Erweiterungen**. Wird nach jedem T aktualisiert.

Abhängigkeit: `forecast_service` aus Feature #4 muss lauffähig sein — dieses Feature rechnet nicht selbst, es ruft nur auf. Siehe dort für Details zur Drei-Topf-Klassifikation, Lohnperioden-Logik etc.

## Vom Issue abweichende Entscheidungen (mit dem Team abgestimmt)

Diese vier Punkte weichen bewusst vom ursprünglichen Issue-Text ab — Entscheidung liegt beim Team, nicht bei mir:

1. **Timeout-Fallback (8s) ist kein stiller Template-Fallback.** Das Issue beschreibt "danach automatischer Fallback auf eine Template-Formulierung aus denselben Zahlen". Stattdessen: bei Timeout bekommt der Nutzer eine explizite Fehlermeldung, dass ein Problem aufgetreten ist — kein Text, der wie eine normale Antwort aussieht, aber nicht vom Modell geprüft wurde.
2. **"Kantine halbieren"-artige `what_if`-Fragen sind nicht abbildbar.** Konsistent mit Feature #4 (keine Kategorie-Prozent-Anpassung in `Simulate`). Solche Fragen laufen in `unsupported` oder eine Rückfrage, nicht in eine erfundene Berechnung.
3. **Folgefragen sind im Scope** (Issue-eigene "offene Frage" positiv entschieden) — der Server hält pro `conversation_id` einen In-Memory-State der letzten Frage/Antwort.
4. **`potential_chf`** pro Hebel = Differenz zum historischen Monats-Minimum der Kategorie (nicht pauschal 50%) — ehrlicher, weil es zeigt, was der Nutzer selbst schon mal geschafft hat.

Weitere Annahmen siehe T0–T13 unten, jeweils im Kontext.

---

## T0 — Setup (openai SDK, Env-Vars, Config)

**Stand:** Fertig — `docker compose up -d --build` startet mit funktionierendem OpenAI-Zugriff, verifiziert mit einem echten Live-Call (`gpt-4o-mini` → "PONG").

**Bugs:** Keine gefunden.

**Entscheidungen/Details:**
- `openai==1.109.1` gepinnt (letzte 1.x-Version, nicht die neueste Major 2.x/3.x) — der Code hier ist gegen die 1.x Structured-Outputs-API (`chat.completions.create(..., response_format=...)`) geschrieben und verifiziert; ein Major-Sprung riskiert eine andere API-Form, die hier nicht getestet ist.
- `OPENAI_API_KEY`/`ASSISTANT_MODE`/`OPENAI_MODEL`/`ASSISTANT_LLM_TIMEOUT_SECONDS` kommen aus `apps/api/app/.env`, injiziert über `env_file:` in `docker-compose.yml` — **zur Laufzeit**, nicht ins Image gebacken (`app/.env` steht jetzt in `.dockerignore`). `.env.example` liegt daneben als Vorlage fürs Team.
- **Fail-fast beim Start:** `ASSISTANT_MODE=live` ohne `OPENAI_API_KEY` lässt den Container mit einer klaren `RuntimeError` sterben, statt später mitten in einem Chat-Request einen kryptischen Auth-Fehler zu werfen. `ASSISTANT_MODE=cached` startet ohne Key. Beide Fälle live gegen ein frisches Container-Image verifiziert (positiv und negativ).
- Neue Config-Defaults (`SALARY_GROWTH_DEFAULT_PCT=1.0`, `INFLATION_DEFAULT_PCT=1.5`, `TIGHT_BUFFER_MONTHS=3`) schon jetzt angelegt, auch wenn sie erst ab T2/T5 verwendet werden — hält alle Tuning-Werte an einem Ort (`core/config.py`), wie bei Feature #4.

**Grenzen:**
- `apps/api/app/.env` muss von jedem Teammitglied lokal aus `.env.example` erstellt werden — ist nicht Teil des Repos (Secret). Ohne diese Datei bricht `docker compose up` mit der Fail-Fast-Meldung ab (dokumentiertes, gewolltes Verhalten, kein Bug).
- Kein Kosten-Tracking/Rate-Limiting auf die OpenAI-Calls — für eine Hackathon-Demo mit wenigen Requests kein Problem, für echten Betrieb fehlend.

**Erweiterungen:**
- `OPENAI_MODEL` könnte pro Aufruf (Extraktion vs. Formulierung) unterschiedlich gesetzt werden (z. B. günstigeres Modell für die Extraktion), aktuell ein einziger Wert für beide.

---

## T1 — schemas/assistant.py

**Stand:** Fertig — alle Modelle importiert und live gegen den laufenden Container getestet (Request/Response-Roundtrip, diskriminierte Chart-Union für alle 3 Typen, Rückfrage-Zustand, unsupported-Zustand, Suggestions, Range-Validierung der Annahmen).

**Bugs:** Keine gefunden. Das aus Feature #4 bekannte Pydantic-Problem (Feldname == Typname bricht mit `Field()` unter `from __future__ import annotations`) trat bewusst nicht auf: `ChartSeriesPoint.date: date` ist absichtlich ohne `Field()`-Aufruf geschrieben (gleiche Lösung wie `NextSalary.date` in Feature #4).

**Design-Entscheidungen:**
- **Nur der öffentliche REST-Contract** ist hier modelliert (`AssistantAskRequest`/`-Response`, `SuggestionsResponse`, Chart-Union). Das interne Structured-Output-Schema für LLM-Call #1 (Extraktion) kommt erst in T3, zusammen mit dem eigentlichen OpenAI-Call — sonst müsste das Schema zweimal entworfen werden, einmal geraten und einmal nach echtem Prompting korrigiert.
- **`AssistantFacts`** ist ein einziges flexibles Modell mit optionalen Feldern für alle drei Intents (dokumentiert, welches Feld zu welchem Intent gehört) statt einer diskriminierten Union pro Intent — konsistent mit `Assumptions.notes` in Feature #4 (Freitext-Erweiterung statt starrer Pro-Fall-Typisierung).
- **`what_if` bleibt auf die 4 bestehenden `Adjustment`-Typen aus Feature #4 beschränkt** (wiederverwendet in T3, hier noch nicht importiert) — Kategorie-Prozent-Fragen wie "Kantine halbieren" laufen in `unsupported`, kein 5. Typ.
- **`potential_chf`** pro Hebel dokumentiert als "historisches Minimum"-Berechnung (deine Entscheidung), nicht die pauschalen 50 % aus dem Issue-Text.
- **`AssumptionsUsed.salary_growth_pct`/`inflation_pct`** sind bei `horizon=present` immer `0` (keine Hochrechnung) — im Docstring festgehalten, damit T2/T5 das konsistent umsetzen.
- **`Chart`** ist eine diskriminierte Union (`type`-Feld) über die 3 festen Chart-Typen, exakt wie die 4 `Adjustment`-Typen in Feature #4 — das Modell wählt nur den Typ, generiert keine eigene Struktur.

**Grenzen:**
- Range-Validierung der Annahmen (`0–5%` Lohnwachstum/Inflation, `0–100%` Sparquote) ist aus dem Issue-Text abgeleitet, nicht kalibriert — reine Plausibilitätsgrenze gegen offensichtlichen Unsinn (z. B. 50 % Lohnwachstum p.a.), keine fachliche Aussage.
- `SuggestionsResponse.suggestions` hat `min_length=3, max_length=5` als Pydantic-Constraint direkt im Schema erzwungen — falls T-spätere Logik das mal nicht einhält, gibt es einen internen 500 statt eines stillen Fehlers. Bewusst so (fail loud), aber erwähnenswert.

**Erweiterungen:**
- `ChartSeriesPoint` wird von allen 3 Chart-Typen geteilt (auch dort, wo z. B. `before_after` eigentlich kein Band braucht) — hält die Typenzahl klein, könnte aber pro Chart-Typ spezifischer werden, falls das Frontend das unbenutzte `lower_chf`/`upper_chf` bei `before_after` verwirrend findet.
