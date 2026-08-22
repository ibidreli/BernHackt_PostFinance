<!-- Title: Status — Future-Me Chatbot (Backend) -->

# Status: Future-Me Chatbot (Szenario-Assistent) — Backend

Lebendes Dokument analog zu [STATUS_FEATURE_NR_4_BACKEND.md](STATUS_FEATURE_NR_4_BACKEND.md). Kompakte API-Referenz: [ASSISTANT_API.md](ASSISTANT_API.md).

Abhängigkeit: `forecast_service` (Feature #4) muss laufen — dieses Feature rechnet nicht selbst, es ruft nur auf.

## Merge mit `main` (T12)

`origin/main` enthielt eine zweite, unabhängige Chatbot-Implementierung (Branch `origin/feature/prognosis`, regelbasierte Extraktion ohne echtes LLM, laut eigener Doku explizit ein Platzhalter — "die KI-Variante ist noch nicht gebaut"). Beim Merge in diesen Branch gewinnt auf deine Entscheidung durchgehend diese (vollständig getestete, LLM-integrierte) Implementierung für `schemas/assistant.py`, `services/assistant_service.py`, `services/intent_service.py`, `api/routes/assistant.py`. Stale Dateien der verworfenen Implementierung entfernt: `tests/test_assistant.py`, `prompts/assistant_extraction.md`, `prompts/assistant_phrasing.md`.

**Offen, nicht mein Auftrag:** Das mitgemergte Angular-Frontend (`apps/web/src/app/core/assistant.ts`) ruft `/api/v1/Ask`/`/api/v1/Suggestions` auf (Pfade der verworfenen Implementierung), nicht `/api/v1/assistant/ask`/`/api/v1/assistant/suggestions`. Frontend ist dadurch inkompatibel — Anpassung wäre Frontend-Arbeit, ausserhalb des Backend-Auftrags.

Nach dem Merge vollständig regressionsgetestet (alle `inspect_*`-Skripte, `/health`, ein echter HTTP-Call).

## Vom Issue abweichende Entscheidungen (mit dir abgestimmt)

1. **Timeout (8s) → expliziter Fehler**, kein stiller Template-Fallback (das Issue beschreibt einen Fallback; deine Korrektur).
2. **"Kantine halbieren"-artige `what_if`-Fragen sind nicht abbildbar** (konsistent mit Feature #4) → `unsupported`, keine erfundene Rechnung.
3. **Folgefragen sind im Scope** — In-Memory-State pro `conversation_id`.
4. **`potential_chf`** = Differenz zum historischen Monats-Minimum der Kategorie, nicht pauschal 50%.
5. **"Steuern" als Hebel ausgeschlossen** (`_NON_DISCRETIONARY_CATEGORY_KEYWORDS`) — auf deine Entscheidung, nachdem es als Spar-Hebel vorgeschlagen wurde.

---

## T0 — Setup

Config/`.env`/Fail-fast fürs OpenAI-Setup. `openai==1.109.1` bewusst gepinnt (1.x-API, nicht die neueste Major). Live verifiziert (echter Call, Fail-fast positiv/negativ getestet).

## T1 — schemas/assistant.py

Public REST-Contract (Request/Response, 3 Chart-Typen als Union). `AssistantFacts` ein flexibles Modell für alle drei Intents statt Union pro Fall.

## T2 — forecast_service: present/1y/5y/10y

`project_long_term()`: RecurringPayments → monatsäquivalente Rate statt Einzel-Termine (über 10 Jahre nicht sinnvoll auflösbar), Wachstum/Inflation über stetige Verzinsung. Fixkosten bleiben nominal flach (deine Entscheidung). Band-Formel von Feature #4 wiederverwendet.
**Beobachtung:** Mit den Sample-Daten ist die Sparquote dünn (~9.8%) — bei 5% Inflation kippt die 5y-Prognose ins Negative. Reale Dateneigenschaft, kein Bug.

## T3 — intent_service.py (Extraktion + Validierung)

`beta.chat.completions.parse()` (Structured Outputs) für LLM-Call #1. Rückfrage-Texte kommen aus einer festen Tabelle, nicht vom Modell. Timeout → `AssistantLLMTimeoutError`.
**Bug gefunden & behoben (vor dem Testen):** totes Code-Fragment liess `default_used` immer `None` sein.
**Fund für T7:** eine sprachlich mehrdeutige Frage ("Möbel") lieferte einen `merchant_hint`, der zu keiner echten RecurringPayment passt — T7 muss den "kein Treffer"-Fall abfangen.

## T4 — Conversation-State

`ConversationStore` (in-memory, `app.state`). Rückfrage gilt nur als beantwortet bei expliziter Bestätigung oder eindeutigem Button-Text-Match, sonst frische Extraktion. Live bewiesen: echte Folgefrage ("2 Jahre länger warten") löst über den gespeicherten Kontext korrekt auf, inkl. Horizont-Rundung auf den nächsten erlaubten Wert.

## T5 — Antwortlogik (yes/tight/no_unless, Hebel)

`_evaluate_target()` — eine Funktion für alle drei Intents (`what_if` mit `target_chf=0`: "bleibt das Szenario gesund?"). `what_if` bei `present` nutzt Feature 4s `simulate()` unverändert, bei 1y/5y/10y ein neuer Vergleichspfad über zwei `project_long_term`-Aufrufe.
**Bug gefunden & behoben:** `months_remaining` rundete bei `present` auf `0` (irreführend) — jetzt `None` bei `present`, `required_monthly_chf` nutzt weiter den exakten Wert.
**Fund (an T8 weitergegeben):** "Weltreise für 15'000" löste die Bar/Leasing-Rückfrage aus (Betrags-Trigger allein reicht nicht).

## T6 — Chart-Auswahl

Reines Mapping `intent → Chart-Typ` (nicht mal ein Modell entscheidet). `time_to_goal` → `goal_progress` (nicht `wealth_over_time`, Issue listet es zweideutig). `what_if` → `before_after`, unabhängig vom Status. Live verifiziert: Chart-Zahlen stimmen exakt mit `facts` überein.

## T7 — assistant_service.py (Orchestrierung)

Kompletter End-to-End-Fluss, live mit echten OpenAI-Calls. `needs_clarification`/`unsupported` rufen nie LLM-Call #2 auf. `services/llm_client.py` neu ausgegliedert (geteilte Fehlerbehandlung für beide LLM-Calls).
**Drei Bugs gefunden & behoben:**
1. Netflix-Kündigung wurde als "Erhöhung" beschrieben (Modell musste Richtung erraten) → neues Feld `adjustment_description` gibt die Handlung fest vor.
2. `buffer_after_months` (Monate) als "CHF 1" formuliert → Einheit im Prompt präzisiert.
3. Interne Schreibweise `"Kategorie // Unterkategorie"` landete wörtlich im Text → Prompt-Anweisung zur natürlichen Umschreibung.

Bug 2 ist der Auslöser für T10 (eine reine "Zahl kommt in facts vor"-Prüfung hätte ihn nicht gefangen).

## T8 — prompts/ (versioniert)

Beide Prompts (aus T3/T7) reviewt, `prompts/README.md` mit Versionierungs-Konvention ergänzt.
**Fund aus T5 hier behoben:** neues Feld `payment_type_relevant` (Modell markiert `false` bei Erfahrungen/Reisen statt physischen Gütern) — "Weltreise" löst jetzt korrekt keine Bar/Leasing-Rückfrage mehr aus. Nicht perfekt: "Hochzeit" bleibt ein Grenzfall, im README als bekannte Grenze benannt.

## T9 — Cache-Modus + Timeout-Fehlermeldung

`cache_service.py`: 5 Demo-Fragen, exaktes Text-Matching, kein LLM. `template_answer()`: deterministische Formulierung direkt aus `facts`. **Härtester Beweis:** OpenAI-Client im Test aktiv blockiert (`AssertionError` bei jedem Aufrufversuch) — alle 5 Fragen inkl. Rückfrage-Flow laufen trotzdem durch.
**Bug gefunden & behoben:** Vorzeichen-Fehler im Template ("Bilanz verbessert sich um CHF -50") — jetzt vorzeichen-bewusst ("verbessert"/"verschlechtert").
`AssistantLLMTimeoutError` kennt jetzt `stage` ("Extraktion"/"Formulierung").

## T10 — Zahlenabgleich

`verification_service.py`: Zahlen werden **typgebunden** geprüft (CHF-Zahl nur gegen CHF-Fakten, Monats-Zahl nur gegen Monats-Fakten) — genau die Lücke, die T7s Bug 2 offengelassen hätte. Fallback nutzt `template_answer()` (T9) wieder. Toleranz: 60 CHF bei 5y/10y (Rundungsvorgabe im Prompt), 1 CHF sonst.
Live verifiziert: historischer Bug wird erkannt, künstlich kaputter LLM-Text wird verworfen und ersetzt, 0 falsch-positive Ablehnungen über 5 echte LLM-Antworten.

## T11 — api/routes/assistant.py

`POST /api/v1/assistant/ask`, `GET /api/v1/assistant/suggestions` — erstmals über echtes HTTP. Fehler-Envelope von Feature 4 wiederverwendet (`{"error": {...}}`), LLM-Fehler → 504/502 statt 500.
**Härtester Beweis:** separater Container **ganz ohne `OPENAI_API_KEY`** im `cached`-Modus liefert über echtes HTTP eine korrekte Antwort.
**Infrastruktur-Fund (kein Code-Bug):** `docker run` mit einem veralteten Image lieferte zunächst 404 — Dev-Container nutzt Live-Reload, ein eigenständiger `docker run` braucht ein frisches `docker compose build`.

---

## Bekannte Grenzen (projektweit)

- Kein automatisiertes Eval-Set für die Prompts — Verifikation über live getestete Einzelfälle in den `inspect_*`-Skripten, kein systematisches Test-Framework.
- LLM-Nichtdeterminismus: dieselbe Folgefrage kann zwischen Läufen leicht unterschiedlich klassifiziert werden (z. B. Horizont oder sogar Intent) — beobachtet, kein Bug, aber erwähnenswert für die Demo.
- Kein TTL/Cleanup für Conversation-States, nicht thread-safe bei parallelen Requests auf dieselbe `conversation_id` — für eine Einzelperson-Demo irrelevant.
- 409 ("kein Saldo") nicht eigenständig über HTTP getriggert (kein `as_of` im Request-Contract) — Route-Code ist identisch zum bereits getesteten Feature-4-Muster.
