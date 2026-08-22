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

---

## T2 — forecast_service-Erweiterung für present/1y/5y/10y

**Stand:** Fertig — `project_long_term()` in `forecast_service.py`, live gegen die echten Daten getestet (alle 3 Horizonte, Band-Null-Breite bei m=0, Savings-Override, Wachstums-/Inflations-Sensitivität, Fixkosten-Flach-Check, 2 Fehlerpfade). `present` selbst braucht keine neue Funktion — mappt 1:1 auf das bestehende `forecast(horizon="next_salary")`, wird erst in T7 verdrahtet.

**Bugs:** Ein Bug bei mir selbst gefunden und korrigiert, bevor er lief: `LongTermForecast` (ein `NamedTuple`) hatte versehentlich `Field(default=0.0)` als Default-Wert kopiert (Pydantic-Reflex aus den Schema-Dateien) — `NamedTuple` kennt kein `Field()`, das wäre ein `NameError` beim Import gewesen. Beim Schreiben direkt aufgefallen und auf einfache Defaults (bzw. gar keine, da jedes Feld im `return` sowieso gesetzt wird) korrigiert, bevor es überhaupt getestet wurde.

**Design-Entscheidungen:**
- **Kein Event-Datums-Modell für 1y/5y/10y.** Die bestehende `_build_series`-Logik (T7, Feature #4) trackt einzelne projizierte Topf-1-Termine — über 10 Jahre/120 mögliche Vorkommen wäre das sowohl unnötig fein aufgelöst als auch potenziell irreführend (welche einzelne Quartalsrechnung in 8 Jahren "wirklich" an diesem Tag fällt, ist nicht seriös vorhersagbar). Stattdessen: jede aktive RecurringPayment wird zu einer monatsäquivalenten Rate zusammengefasst (Einkommen und fixe Ausgaben separat), Wachstum/Inflation wirken auf diese Rate über stetige monatliche Verzinsung aus der Jahres-Prozentangabe.
- **Monatliche Auflösung für alle drei Horizonte** (nicht vierteljährlich für 5y/10y, wie ich in der Planung ursprünglich vorgeschlagen hatte) — die Payload-Sorge war unbegründet: 121 Punkte à 4 Zahlen sind ~6 KB, kein Problem. Einfacher (eine Auflösung statt zwei) schlägt die vorzeitige Optimierung.
- **Fixkosten bleiben nominal flach** (deine Entscheidung) — `monthly_fixed_expense_chf` ist unabhängig von `inflation_pct`, live verifiziert.
- **Band-Formel wiederverwendet** exakt die sqrt-gedämpfte Spread-Logik aus `_build_series` (Feature #4, dort bereits gegen den Pitch-Fund "Band wirkt nicht kompetent" kalibriert) — der Spread selbst wird zusätzlich mit demselben Inflationsfaktor wie die variablen Ausgaben skaliert, damit die *relative* Bandbreite über den Horizont konsistent bleibt.
- **`savings_rate_pct`-Override ersetzt nur die Erwartungswert-Berechnung**, nicht das Band — die Unsicherheit kommt weiterhin aus der echten Streuung der variablen Ausgaben, nicht aus einer geratenen Bandbreite um eine überschriebene Sparquote.
- **Einkommensbasis nutzt alle aktiven wiederkehrenden Einnahmen** (nicht nur die eine per `detect_salary_recurring` erkannte "Lohnzahlung"), monatsäquivalent summiert — vollständiger als nur den einen erkannten Lohn, falls z. B. eine zweite regelmässige Einnahmequelle existiert. `salary_growth_pct` wirkt vereinfachend auf diese gesamte Basis, nicht nur auf die einzelne Lohnzahlung — dokumentiert als bewusste Vereinfachung.

**Beobachtung, kein Bug:** Mit den echten Beispieldaten ist die Sparquote aus der Historie sehr dünn (~9.8 %: CHF 2213 Einkommen ./. CHF 1880 variable ./. CHF 115 fixe Ausgaben ≈ CHF 218/Monat). Bei 5 % Inflations-Annahme kippt die 5-Jahres-Prognose ins Negative (CHF −1'317 statt +13'376 bei 0 % Inflation). Das ist eine reale Eigenschaft der Beispieldaten, keine Fehlfunktion — im Pitch aber erwähnenswert, falls mit den Reglern demonstriert wird: bei diesem Datensatz reagiert die Prognose sichtbar empfindlich auf die Inflations-Annahme, was die "Annahmen sind sichtbar und wirken"-Anforderung eher gut zeigt als kaschiert.

**Grenzen:**
- Das 1-Jahres-Band ist bei den echten Daten recht breit (m=12: CHF −318 bis CHF 5'956 bei erwartet CHF 2'878) — direkte Folge von nur 6 Monaten Ausgabenhistorie mit hoher Varianz, nicht neu kalibriert über die bereits in Feature #4 abgenommene Formel hinaus. Falls das im Pitch "unruhig" wirkt, wäre eine erneute, gezielte Dämpfung eine eigene Entscheidung (wie bei Feature #4's Band-Fix) — hier nicht selbständig verändert, da nicht beauftragt.
- Kein Zins/Rendite (`interest_applied` bleibt `false`, wird erst in T5 ins `assumptions_used`-Feld geschrieben) — reine Summierung wie in Feature #4.
- `wait_months`/Korridor-Suche über den sichtbaren Horizont hinaus ist hier noch nicht gebaut — `project_long_term` akzeptiert bewusst eine freie `months`-Zahl (nicht nur 12/60/120), damit T5 bei Bedarf einfach mit einer grösseren Zahl erneut aufrufen kann, ohne diese Funktion zu ändern.

**Erweiterungen:**
- `LONG_HORIZON_MONTHS` ist ein einfaches `dict[str, int]`, kein `Literal`-gebundener Typ — T5/T7 müssen selbst sicherstellen, dass nur gültige `AssistantHorizon`-Werte reinkommen (Pydantic übernimmt das schon auf Request-Ebene, T1).
- Aktuell wird die variable Basis (Median/P25/P75) einmalig bei `as_of` berechnet und dann über den ganzen Horizont hochskaliert — eine Erweiterung wäre, saisonale Muster (z. B. höhere Ausgaben im Dezember) zu modellieren, was mit nur 6-12 Monaten Historie aber nicht seriös möglich ist.

---

## T3 — services/intent_service.py (LLM-Extraktion + Validierung)

**Stand:** Fertig — live gegen die echte OpenAI-API getestet (8 reale Fragen über alle drei Fragetypen + unsupported + category-percent-Fall + 2 Rückfrage-Trigger), plus 2 Fehlerpfade (Timeout, ungültiger Key) und die deterministische Clarification-Answer-Logik ohne LLM-Call.

**Bugs:** Ein Bug beim Schreiben selbst gefunden und vor dem Testen korrigiert: in `apply_clarification_answer` blieb ein totes Code-Fragment (`answer_text if False else None`) aus einer Zwischenversion stehen — hätte `default_used` fälschlich immer auf `None` gesetzt, egal ob ein Default angewendet wurde. Beim Nochmal-Lesen vor dem Testen aufgefallen, bereinigt, danach live verifiziert (Test bestätigt: Freitext-Antwort ohne Button-Match → `default_used="Bar"`).

**Design-Entscheidungen:**
- **Drei Dinge in einer Datei** (Schema, LLM-Call, Validierungs-Leiter) statt aufgeteilt — sie gehören eng zusammen (`ExtractedIntent` wird von allen dreien verwendet) und die Datei bleibt trotzdem überschaubar.
- **`beta.chat.completions.parse()` mit Pydantic-Modell als `response_format`** (Structured Outputs, live gegen `gpt-4o-mini` verifiziert) statt manuellem JSON-Parsing — die SDK übernimmt Schema-Generierung und Validierung.
- **Timeout wandelt sich in eine explizite Exception** (`AssistantLLMTimeoutError`), keine stille Ersatzformulierung — deine Korrektur von eben, live mit einem künstlichen 0.01s-Timeout verifiziert.
- **Rückfrage-Texte/Optionen kommen aus einer festen Tabelle** (`_FIXED_CLARIFICATIONS`), nicht vom Modell — erfüllt die Issue-Vorgabe wörtlich ("fest definiert, nicht vom Modell erfunden").
- **Clarification-Antworten brauchen keinen LLM-Call.** Buttons liefern immer eine von wenigen bekannten Zeichenketten — `apply_clarification_answer` matched deterministisch und wendet bei Nichterkennung (Freitext statt Klick) einen dokumentierten Default an, inkl. der von der Issue geforderten Rückmeldung ("...ich habe Bar angenommen").
- **Priorität der Validierungs-Leiter** (Reihenfolge fest im Code): fehlender Betrag zuerst (ohne den ist nichts berechenbar), dann fehlender Zeitraum bei `present` (eine "kann ich mir X leisten"-Frage ohne Horizont ergibt bei `present` keinen Sinn), dann Zahlungsart bei grossen Beträgen, dann what_if-Spezifika — so löst nie mehr als eine Rückfrage gleichzeitig aus.
- **`merchant_hint` fehlt bei cancel/adjust → `unsupported`, keine 5. Rückfrage.** Bewusst nicht selbständig um einen neuen Trigger erweitert, der nicht im vom Team abgesegneten 3er-Set steht.

**Echter Fund, an T7 weiterzugeben:** Bei der Frage *"Was wäre, wenn ich monatlich 50 mehr für Möbel ausgebe?"* hat das Modell trotz Prompt-Hinweis ("bestehende wiederkehrende Zahlung") `adjustment_kind="adjust"` mit `merchant_hint="Möbel"` extrahiert, obwohl "Möbel" mit ziemlicher Sicherheit keine bestehende RecurringPayment in den echten Daten ist — sprachlich ist die Frage tatsächlich mehrdeutig (auch für einen Menschen). `validate_extraction` prüft nur, dass *irgendein* `merchant_hint` da ist, nicht ob er zu echten Daten passt (kann sie nicht sehen, bewusste Entkopplung). **T7 muss** beim Abgleich von `merchant_hint` gegen echte `RecurringPayment`-Namen den Fall "kein Treffer trotz cancel/adjust" abfangen (z. B. Fallback auf `unsupported` statt Absturz) — hier vorgemerkt, damit es beim Bau von T7 nicht vergessen geht.

**Grenzen:**
- Kein Retry bei transienten OpenAI-Fehlern (z. B. einzelner 500er) — ein Fehlschlag ist sofort ein Fehlschlag. Für eine Live-Demo mit wenigen Anfragen akzeptabel, für echten Betrieb zu simpel.
- `_parse_amount` ist eine einfache Regex (erste Zahl im Text) — findet "CHF 30'000.-" korrekt, würde aber bei mehreren Zahlen im Freitext (z. B. "30000 oder vielleicht 35000") die erste nehmen, nicht unbedingt die gemeinte.
- Der System-Prompt (`prompts/intent_extraction_v1.md`) ist v1, nicht gegen eine grössere Fragen-Stichprobe kalibriert — die 8 Testfragen oben sind alle plausibel korrekt, aber kein systematisches Eval-Set.

**Erweiterungen:**
- Ein kleines Few-Shot-Beispiel-Set im Prompt (aktuell nur inline-Beispiele in der Erklärung, keine expliziten Input→Output-Paare) könnte Grenzfälle wie den "Möbel"-Fund oben zuverlässiger machen.
- `ClarificationAnswer.default_used` könnte künftig auch bei `target_chf` einen Hinweis liefern (aktuell `None`, da es dort keinen sinnvollen Default-Betrag gibt) - bewusst so gelassen, aber falls das Frontend hier auch eine Meldung erwartet, müsste `validate_extraction`/T7 das nachziehen.
