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

---

## T4 — Conversation-State (in-memory, Folgefragen-Basis)

**Stand:** Fertig — `ConversationStore` in `app.state` verdrahtet (main.py), live getestet inkl. eines echten End-to-End-Beweises der Folgefrage-Auflösung mit einem echten `extract_intent()`-Call.

**Bugs:** Keine gefunden.

**Design-Entscheidungen:**
- **`last_extracted` speichert die finalen, nach einer eventuellen Rückfrage-Antwort zusammengeführten Parameter**, nicht die rohe Erst-Extraktion — eine Folgefrage muss sich auf das beziehen können, was tatsächlich berechnet wurde, nicht auf einen Zwischenstand.
- **`build_prior_turn_summary()` erzeugt Freitext, kein JSON** — der Kontext ist für das Sprachmodell gedacht (LLM-Call #1 liest ihn), nicht für Code, das ihn zurückparst.
- **`resolve_pending_clarification()` ist bewusst konservativ:** Eine offene Rückfrage wird nur dann als beantwortet behandelt, wenn der Client das Feld explizit bestätigt (`context.pending_clarification`) ODER der Text eindeutig zu einer der festen Button-Optionen passt. Bei allem anderen (z. B. der Nutzer stellt trotz offener Rückfrage eine völlig neue Frage) wird die alte Rückfrage stillschweigend fallengelassen und frisch extrahiert — verhindert, dass eine unrelated neue Frage fälschlich als "Antwort" auf die alte Rückfrage fehlinterpretiert wird.
- **Live verifiziert, nicht nur mit Fake-Daten:** Turn 1 und die Folgefrage sind beide echte `extract_intent()`-Aufrufe gegen die reale OpenAI-API. Ergebnis: "Und wenn ich 2 Jahre länger warte?" (nach "...in 5 Jahren ein Auto für 30000...") wurde korrekt als `target_chf=30000`, `target_label="Auto"` (aus dem Kontext übernommen) und `horizon_override="10y"` aufgelöst — das Modell hat "5 Jahre + 2 Jahre" richtig auf den nächstliegenden erlaubten Horizont (10y statt 5y, da nur `present`/`1y`/`5y`/`10y` erlaubt sind) gerundet, ohne dass das im Prompt explizit vorgegeben war.

**Grenzen:**
- Kein TTL/Cleanup — Zustände bleiben bis zum Neustart im Speicher (dokumentierte, akzeptierte Grenze, konsistent mit "keine Datenbank" im ganzen Projekt).
- Nicht thread-safe gegen zwei gleichzeitige Requests auf dieselbe `conversation_id` (Dict ohne Lock) — für eine Live-Demo mit einer tippenden Person irrelevant.
- `resolve_pending_clarification`'s Text-Match-Fallback (Fall B oben) ist ein simpler Lowercase-String-Vergleich, kein Fuzzy-Match — "leasing bitte" statt "Leasing" würde NICHT erkannt und liefe stattdessen in eine frische Extraktion (die vermutlich trotzdem sinnvoll wäre, da die Frage kontextuell noch erkennbar ist, aber nicht getestet).

**Erweiterungen:**
- `ConversationStore.__len__` ist als kleiner Health-Check-Hook gedacht (z. B. `/health` könnte später `len(app.state.conversation_store)` zeigen) - aktuell noch nirgends verdrahtet.

---

## T5 — Antwortlogik (yes/tight/no_unless, Hebel)

**Stand:** Fertig — `services/answer_service.py`, live gegen echte Daten getestet: Hebel-Sortierung, alle drei Zustände (garantiertes no_unless mit riesigem Ziel, garantiertes yes/tight mit 0-CHF-Ziel), Horizont-Konsistenz (1y/5y/10y liefern alle ein Ergebnis), `time_to_goal` mit Korridor-Suche, `what_if` für alle 4 Adjustment-Typen über beide Rechenpfade (present via Feature-4-`simulate()`, 1y/5y/10y via `project_long_term`), der `UnresolvedAdjustmentError`-Pfad, und ein echter End-to-End-Beweis (`extract_intent()` → `answer_affordability()`).

**Bugs:** Einen echten Bug beim Testen gefunden und behoben: `months_remaining` bei `horizon="present"` wurde als gerundete Ganzzahl gemeldet — bei einem Bruchteilsmonat wie 0.1–0.4 (wenige Tage bis zum nächsten Lohn) rundete das auf **0**, was fälschlich wie "keine Zeit mehr übrig" aussieht. Live reproduziert (0-CHF-Ziel-Test zeigte `months_remaining: 0`), behoben durch `None` bei `present` statt einer irreführenden gerundeten Zahl — `required_monthly_chf` selbst nutzt weiterhin den exakten Bruchteilswert, nur die Anzeige war betroffen.

**Zwei Erweiterungen an bereits bestehendem Code (T2/Feature #4), um Duplikation zu vermeiden statt sie in T5 nachzubauen:**
- `LongTermForecast` (T2) um `monthly_expenses_at_horizon_end_chf` ergänzt (fixe + inflationierte variable Ausgaben am Horizontende) — sonst hätte T5 die Zinseszins-Formel aus T2 duplizieren müssen.
- `CategoryStats` (Feature #4, `transaction_repository.py`) um `min_chf` ergänzt (echtes historisches Monats-Minimum, nicht P25) — Basis für `potential_chf`. Rückwärtskompatibel (neues Feld, keine bestehende Nutzung geändert), gegen den laufenden Container verifiziert (T2/T4-Health-Check weiterhin grün).
- `forecast_service._apply_adjustments` → `apply_adjustments` (öffentlich gemacht) — T5 braucht sie für den 1y/5y/10y-what_if-Pfad (modifizierte `recurring_payments`-Liste in `project_long_term` einspeisen).

**Design-Entscheidungen:**
- **`_evaluate_target` ist eine einzige geteilte Funktion** für `affordability`, `time_to_goal` UND `what_if` — bei `what_if` mit `target_chf=0.0` aufgerufen ("bleibt das Szenario finanziell gesund?"), keine drei separate Zustands-Logiken. Live verifiziert: alle drei Pfade liefern konsistent einen der drei Zustände, nie ein rohes Ja/Nein.
- **`what_if` bei `present` nutzt Feature 4s echtes `simulate()` unverändert** (exakt, ereignis-datiert), **bei 1y/5y/10y einen neuen Vergleichspfad** über zwei `project_long_term`-Aufrufe (Baseline vs. mit modifizierten `recurring_payments`) — konsistent mit der bereits in T2 getroffenen "present = bestehende Funktion, 1y/5y/10y = neues Aggregat-Modell"-Aufteilung.
- **`one_off` bei 1y/5y/10y wird als konstanter Shift ab Tag 0 modelliert**, nicht als Ereignis zu einem bestimmten Datum — da T3 kein Datum extrahiert (Rückfrage-Set deckt das nicht ab) und `resolve_adjustment` das Datum deshalb immer auf `as_of` setzt, ist "ab jetzt permanent tiefer" exakt richtig, keine Näherung. Live mit einer Kontrollrechnung verifiziert (exakt −2000 CHF am Horizontende bei einer einmaligen 2000-CHF-Ausgabe).
- **`add_recurring` nutzt immer `interval="monthly"`** als Default — T3 extrahiert keine Periodizität (nicht Teil des fixen Rückfrage-Sets).
- **`_match_merchant`** ist ein simpler Case-insensitive-Substring-Match mit "kürzester Treffer gewinnt" als Tie-Break bei mehreren Kandidaten — bewusst simpel, kein Fuzzy-Matching.

**Echter Fund beim Testen, nicht behoben (ausserhalb T5s Scope):** Die Frage *"Kann ich mir in 5 Jahren 15000 Franken für eine Weltreise leisten?"* löste beim echten End-to-End-Test die "Bar oder Leasing?"-Rückfrage aus (`target_chf=15000 >= LARGE_PURCHASE_THRESHOLD_CHF`). Inhaltlich unpassend — eine Weltreise least man nicht. Der Trigger in T3 ist rein betragsbasiert und unterscheidet nicht zwischen finanzierbaren Gütern (Auto, Möbel) und Erlebnissen/Reisen. Für eine spätere Verfeinerung des Extraktions-Prompts (T8) vorgemerkt, hier nicht selbständig behoben, da es T3s Zuständigkeit betrifft, nicht T5s.

**Grenzen:**
- `_compute_wait_months` ist eine grobe Schätzung mit der heutigen Sparrate, keine erneute Simulation mit Wachstum über die Wartezeit — für eine "wie lange noch"-Hausnummer ausreichend, nicht exakt.
- Bei `savings_rate_pct`-Override bleibt das Band (Unsicherheit) weiterhin aus der echten Ausgaben-Streuung, nicht aus der überschriebenen Sparquote — dokumentierte Vereinfachung aus T2, hier unverändert übernommen.
- Kein Caching zwischen mehrfachen `project_long_term`-Aufrufen innerhalb einer Antwort (z. B. `answer_affordability`'s "present"-Pfad ruft sowohl `forecast()` als auch `project_long_term(months=1)` auf) — für die paar Requests einer Demo irrelevant, bei echtem Traffic zu prüfen.

**Erweiterungen:**
- `resolve_adjustment`/`_match_merchant` könnten künftig mehrere Kandidaten zurückmelden statt still den kürzesten zu wählen, falls das Frontend eine Auswahl anbieten will.

---

## T6 — Chart-Auswahl-Logik

**Stand:** Fertig — `services/chart_service.py`, live gegen echte `AnswerResult`-Objekte aus T5 getestet, inkl. Konsistenz-Checks zwischen Chart-Zahlen und `facts`-Zahlen.

**Bugs:** Keine gefunden.

**Design-Entscheidungen:**
- **Chart-Typ hängt nur vom `intent` ab, nie vom `status`.** Das Issue listet `before_after` unter "what_if, no_unless", was zunächst wie eine vierte Bedingung aussieht - interpretiert als "before_after wird für what_if benutzt, auch wenn dessen Status no_unless ist", nicht als eigener Trigger. Live verifiziert: ein erzwungenes `no_unless`-`what_if` (CHF 5000/Monat zusätzliche Ausgabe) bekommt weiterhin `before_after`, nicht `wealth_over_time`.
- **`time_to_goal` bekommt `goal_progress`, nicht `wealth_over_time`**, obwohl das Issue es in beiden Zeilen der Tabelle listet - Auflösung der Doppel-Zuordnung zugunsten des spezifischeren Charts, das exakt um die drei Korridor-Daten (`goal_date`/`_earliest`/`_latest`) gebaut ist, die T5 für `time_to_goal` ohnehin schon berechnet.
- **Reines Mapping, keine LLM-Beteiligung** - noch strikter als die Issue-Formulierung "das Modell wählt nur den Typ": hier wählt nicht mal ein Modell, es ist eine feste Funktion von `intent`. Unmöglich, in der Demo den falschen Chart-Typ zu bekommen.
- **`ChartSeriesPoint` (Präsentationsschicht, T1) bleibt bewusst ein eigener Typ** getrennt von `SeriesPoint` (Rechenschicht, Feature #4/T2) - `_to_chart_points` ist der einzige Übersetzungspunkt dazwischen.

**Grenzen:**
- Kein Downsampling der Chart-Punkte - bei 10y sind das 121 Punkte, für die drei Chart-Typen bisher unproblematisch (siehe T2s Payload-Grössenabschätzung), aber nicht explizit fürs Charting nochmal geprüft.

**Erweiterungen:**
- Aktuell keine.

---

## T7 — services/assistant_service.py (Orchestrierung inkl. Folgefragen)

**Stand:** Fertig — vollständiger End-to-End-Test, komplett mit echten OpenAI-Calls (kein Mock), inkl. Zwei-Turn-Rückfrage-Flow, echter Folgefrage über Conversation-State, `unsupported` ohne LLM-Call #2, und allen drei Intents.

**Vorgezogen aus T8/T10, weil T7 sonst nicht end-to-end testbar gewesen wäre:** Der Formulierungs-Prompt (`prompts/answer_formulation_v1.md`) und `services/formulation_service.py` (LLM-Call #2) wurden hier gebaut, nicht erst in T8 - exakt das gleiche Vorgehen wie bei T3, wo der Extraktions-Prompt sofort mitgebaut wurde. T8 wird diesen Prompt daher eher review/polish sein als Neubau. `services/llm_client.py` neu ausgegliedert (OpenAI-Client + `AssistantLLMError`/`AssistantLLMTimeoutError`), damit Extraktion und Formulierung dieselbe Timeout-/Fehlerbehandlung teilen, statt sie zu duplizieren - `intent_service.py` re-exportiert die Typen für Abwärtskompatibilität.

**Bugs (drei gefunden und behoben, alle live reproduziert und danach live verifiziert):**

1. **Falsche Handlungsrichtung bei `what_if`.** Eine Netflix-*Kündigung* (positiver Effekt) wurde vom Formulierungs-Modell als *"Erhöhung deiner Netflix-Ausgaben"* beschrieben - die Zahlen stimmten, die beschriebene Handlung war falsch. Ursache: das Modell musste die Richtung aus dem Vorzeichen von `impact_monthly_chf` erraten, bekam aber nie gesagt, was tatsächlich passiert (Kündigen vs. Anpassen vs. Hinzufügen). Behoben mit einem neuen, deterministisch in T7 gebauten Feld `adjustment_description` (z. B. `"Netflix" wird gekündigt und entfällt komplett.`), das die Handlung fest vorgibt statt sie zu erraten.
2. **`buffer_after_months` als CHF-Betrag missverstanden.** Bei `status=tight` formulierte das Modell *"Der Restpuffer beträgt nur CHF 1"* - der Wert (1.1) ist aber in **Monaten**. Die Zahl selbst stand korrekt in `facts` (eine reine "steht die Zahl irgendwo in facts"-Prüfung hätte das NICHT gefangen, siehe unten). Behoben durch explizite Einheiten-Klarstellung im Prompt.
3. **Interne Kategorie-Schreibweise `"Hauptkategorie // Unterkategorie"`** (Feature-4-API-Konvention) landete wörtlich im Chat-Text ("im Bereich Freizeit // Gastronomie"). Behoben durch eine Prompt-Anweisung, das natürlich umzuschreiben - die API-Konvention selbst bleibt unverändert (Feature-4-Code nicht angefasst).

**Wichtiger Fund für T10 (Zahlenabgleich), noch nicht selbst gebaut:** Bug #2 oben zeigt konkret, dass eine reine Zahlen-Existenz-Prüfung ("kommt diese Zahl in `facts` vor?") nicht ausreicht - `1` bzw. `1.1` stand ja tatsächlich in `facts.buffer_after_months`, nur mit der falschen Einheit verknüpft. T10 muss das berücksichtigen, wenn es die automatische Verifikation baut.

**Echter Fund, mit dir abgestimmt und behoben:** Die Kategorie **"Finanzen // Steuern"** tauchte als einer der Top-3-Hebel auf ("könntest du im Bereich Steuern CHF 275 sparen") - inhaltlich fragwürdig, da Steuern kein freiwillig kürzbarer Posten sind. Auf deine Entscheidung hin ("gezielt ausschliessen") in `answer_service.compute_levers` (T5) behoben: `_NON_DISCRETIONARY_CATEGORY_KEYWORDS = ("steuer",)`, ein schmales, benanntes, begründetes Keyword-basiertes Ausschlusskriterium (nicht ein einzelner hartcodierter Kategoriename, nicht eine breite "was ist diskretionär"-Heuristik) - dokumentiert als bewusste Ausnahme von der sonst durchgehenden "aus der Historie erkannt, nicht hartcodiert"-Linie, weil das datengetriebene Ergebnis hier aktiv irreführend gewesen wäre. Live verifiziert: "Steuern" ist raus, "Sonstige Ausgaben" rückt als dritter Hebel nach (Kategorie-Label selbst ist etwas unspezifisch, aber inhaltlich nicht falsch - im Gegensatz zu Steuern).

**Beobachtung, keine Fehlfunktion:** Bei Folgefragen kann das Extraktions-Modell zwischen Läufen leicht unterschiedlich interpretieren - z. B. wurde "Und wenn ich 2 Jahre länger warte?" nach einer `affordability`-Frage in einem Testlauf als `affordability` (Horizont 5y) und in einem anderen als `time_to_goal` (Horizont 1y) klassifiziert. Beide Interpretationen sind für sich genommen plausibel, das System bleibt in beiden Fällen intern konsistent (Chart-Typ folgt korrekt dem jeweiligen Intent). Keine Reparatur nötig, aber erwähnenswert für die Live-Demo: dieselbe Folgefrage kann leicht unterschiedlich beantwortet werden.

**Design-Entscheidungen:**
- **`needs_clarification` und `unsupported` rufen NIE LLM-Call #2 auf** - die Rückfrage selbst bzw. die feste Ablehnungs-Antwort sind bereits der komplette Antworttext, code-generiert. Spart einen LLM-Call und hält diese beiden Zustände 100 % deterministisch.
- **Rückfrage-Antworten laufen nie durch `validate_extraction` ein zweites Mal** (Issue: max. eine Rückfrage pro Anfrage) - fehlt danach immer noch ein Betrag, wird direkt `unsupported` zurückgegeben statt eine zweite Rückfrage zu starten.
- **`conversation_store.clear()` bei `unsupported`**, damit eine völlig andere Folgefrage nicht versehentlich an einen alten, jetzt irrelevanten Zustand anknüpft.
- **State wird auch bei Rückfrage-Auflösung neu gespeichert** (mit `pending_clarification=None`), nicht gelöscht - eine ECHTE Folgefrage nach einer aufgelösten Rückfrage muss weiterhin funktionieren (live verifiziert: Schritt 5 im Test).

**Grenzen:**
- Kein Retry bei einem gescheiterten LLM-Call #2, nachdem LLM-Call #1 schon gelaufen ist - ein Formulierungs-Fehler verwirft die bereits fertige Berechnung komplett (kein Zwischenspeichern/Fortsetzen). Für eine Demo mit einzelnen Anfragen akzeptabel.
- `_describe_adjustment` deckt nur die 4 bekannten Adjustment-Typen ab, kein Fallback-Text falls `adjustment_kind` aus irgendeinem Grund doch `None` erreicht (sollte durch T3s Validierung ausgeschlossen sein, aber nicht defensiv doppelt abgesichert).

**Erweiterungen:**
- `ask()` könnte den `source`-Wert schon jetzt differenzieren, aktuell immer `"live"` - wird erst mit T9 (Cache-Modus) tatsächlich `"cached"` liefern können.

---

## T8 — prompts/ (System-Prompts versioniert)

**Stand:** Fertig — beide Prompts existierten bereits (T3/T7), hier reviewt, ein `prompts/README.md` mit Versionierungs-Konvention ergänzt, und ein während des Reviews gefundener echter Fund behoben.

**Bugs:**
- **Dokumentations-Fehler:** Der Kommentar-Header in `intent_extraction_v1.md` verwies auf eine nicht existierende Datei `intent_formulation_v1.md` statt der echten `answer_formulation_v1.md`. Beim Review gefunden, korrigiert.

**Echter Fund, live behoben (nicht nur Doku):** Beim Review von T5s offen gelassenem "Weltreise löst Bar/Leasing-Rückfrage aus"-Fund (siehe T5) direkt hier angegangen, weil es sich um genau die Art Prompt-Verfeinerung handelt, für die T8 da ist:

- Neues Feld `ExtractedIntent.payment_type_relevant: bool` (Default `true`) - das Modell markiert `false`, wenn `target_label` eine Erfahrung/Dienstleistung ist (Reise, Ferien, Ausbildung, Event) statt eines physischen, finanzierbaren Guts.
- `validate_extraction`s Bar/Leasing-Trigger prüft jetzt zusätzlich dieses Feld.
- Live verifiziert an 5 Fällen: "Weltreise" (15'000 und 8'000 CHF) löst jetzt korrekt **keine** Rückfrage mehr aus (`validation: ok`), "Auto"/"Töff" weiterhin korrekt schon. Kompletter Regressionstest über T3 (`inspect_intent`) und T5 (`inspect_answer`, inkl. des echten End-to-End-Pfads) danach erneut grün.
- **Nicht perfekt, dokumentiert statt verschwiegen:** "Kann ich mir eine Hochzeit für 20'000 leisten?" löst weiterhin die Rückfrage aus (`payment_type_relevant=true`) - ein echter Grenzfall, den das Modell anders zieht als ein Mensch es vielleicht täte. Im `prompts/README.md` explizit als bekannte Grenze benannt statt stillschweigend als "gelöst" zu behandeln.

**Design-Entscheidungen:**
- **`prompts/README.md`** dokumentiert die Versionierungs-Konvention: Solange eine Version aktiv in Entwicklung ist, wird sie in-place korrigiert (kein Versionssprung pro Fix) - ein neuer `_v2`-Dateiname ist für inhaltlich bedeutsame Wechsel nach dem Go-Live gedacht, mit der alten Version weiterhin im Repo zur Nachvollziehbarkeit.
- Beide Prompts bleiben strikt rollenbeschränkt (Extraktion entscheidet nichts, Formulierung rechnet nichts) - im README nochmal explizit zusammengefasst, weil das Issue ausdrücklich sagt, dass die technische Jury danach fragen wird.

**Grenzen:**
- Kein automatisiertes Eval-Set für die Prompts - Verifikation ist die Menge der live gegen die echte API getesteten Fragen in den `inspect_*`-Skripten, kein systematisches Prompt-Testing-Framework. Für eine Hackathon-Zeitspanne bewusst nicht gebaut.
- `payment_type_relevant` ist eine Heuristik des Sprachmodells, keine feste Liste - kann bei ungewöhnlichen Formulierungen weiterhin daneben liegen (siehe Hochzeit-Beispiel).

**Erweiterungen:**
- Ein kleines Few-Shot-Beispiel-Set für Grenzfälle wie "Hochzeit" könnte die `payment_type_relevant`-Erkennung schärfen, ohne eine hartcodierte Liste zu brauchen.

---

## T9 — Cache-Modus + Timeout-Fehlermeldung

**Stand:** Fertig — `services/cache_service.py` (5 Demo-Fragen, exaktes Text-Matching, kein LLM), `template_answer()` in `services/formulation_service.py` (deterministische Formulierung ohne LLM), `ask()` um `mode`-Parameter erweitert. Live verifiziert mit einem harten Beweis: der OpenAI-Client wird im Test per `unittest.mock.patch` komplett blockiert (wirft `AssertionError` bei jedem Aufrufversuch) - alle 5 Demo-Fragen inkl. Rückfrage-Flow laufen trotzdem durch. Das zeigt echte Offline-Fähigkeit, nicht nur "der Code sieht so aus, als würde er das LLM überspringen".

**Bugs (einer gefunden und behoben):**
- **Vorzeichen-Fehler im Template:** Bei einer `what_if`-Anpassung mit negativer Wirkung (z. B. eine neue Ausgabe) stand *"die Bilanz verbessert sich um CHF -50"* - grammatisch falsch und inhaltlich irreführend (liest sich wie eine Verbesserung). Behoben mit einer vorzeichen-bewussten Formulierung (`_impact_phrase`): "verbessert"/"verschlechtert" plus Betrags-Betrag, live verifiziert am Fitness-Beispiel.

**Design-Entscheidungen:**
- **Cache-Matching ist exaktes (normalisiertes) Text-Matching, kein Fuzzy-Match.** Bewusst ehrlich gehalten: das ist ein kontrollierter Demo-Fallback ("WLAN streikt in der Halle"), keine allgemeine Offline-NLU. Im README/STATUS klar so benannt statt eine Fuzzy-Matching-Fähigkeit vorzutäuschen, die nicht wirklich da ist.
- **`template_answer()` ist NICHT dieselbe Funktion wie der im Issue erwähnte "Timeout-Fallback auf Template-Formulierung"** - die gibt es laut deiner Korrektur nicht mehr (Timeout = expliziter Fehler). `template_answer()` ist ausschliesslich für `ASSISTANT_MODE=cached` da. Beide Mechanismen wurden im Issue-Text zusammen erwähnt, sind hier aber bewusst getrennt: der eine ersetzt einen nicht verfügbaren LLM-Call planmässig (Cache), der andere macht einen fehlgeschlagenen LLM-Call sichtbar (Timeout-Fehler).
- **`template_answer()` liest Zahlen direkt aus `facts`/`levers`** - kann per Konstruktion nie einer angezeigten Zahl widersprechen, im Gegensatz zum LLM-Pfad (dafür existiert T10). Bewusst inhaltlich an dieselben Regeln wie `answer_formulation_v1.md` angelehnt (welcher Status nennt was, CHF-Rundung auf 100 bei 5y/10y, Monate statt CHF bei Puffer/Wartezeit), damit beide Pfade sich für den Nutzer konsistent anfühlen.
- **5 Demo-Fragen, hart im Code hinterlegt** mit `ExtractedIntent`-Werten, die aus echten `extract_intent()`-Läufen stammen (nicht erfunden) - siehe `cache_service.py`. Bewusst eine Mischung: 2 lösen realistisch eine Rückfrage aus (beweist, dass der Rückfrage-Flow auch offline funktioniert, da `resolve_pending_clarification`/`apply_clarification_answer` nie ein LLM brauchen), 3 beantworten direkt über alle drei Intents und beide `what_if`-Aktionstypen (cancel/add) hinweg.
- **`AssistantLLMTimeoutError` kennt jetzt `stage`** ("Extraktion" oder "Formulierung") - macht die künftige HTTP-Fehlermeldung (T11) präzise statt eines generischen "etwas ist timeout".
- **`mode` wird zur Aufrufzeit aus `ASSISTANT_MODE` gelesen, nicht als eingefrorener Funktions-Default** - vermeidet Staleness bei Hot-Reload/Tests, konsistent mit T0s "keine versteckten globalen Zustände"-Linie.

**Beobachtung, keine Fehlfunktion:** Die Netflix-Demo-Frage liefert bei `horizon=present` einen wenig eindrücklichen `impact_cumulative_chf=0.0` (Netflix fällt einfach nicht in das enge "bis zum nächsten Lohn"-Fenster) - für den Pitch sollte diese Demo-Frage mit einem längeren Horizont (1y/5y) über den Umschalter gestellt werden, nicht bei `present`. Kein Code-Problem, reine Demo-Empfehlung.

**Grenzen:**
- Die 5 Demo-Fragen sind exakt (normalisiert) zu matchen - Gross-/Kleinschreibung, Leerzeichen und Satzzeichen am Ende werden toleriert, Umformulierungen nicht. `GET /suggestions` (T11) sollte diese exakten Texte als Chips anbieten, damit ein Klick immer trifft.
- Kein Mechanismus, der prüft, ob die 5 hartcodierten `ExtractedIntent`-Werte noch zur aktuellen Prompt-Version passen, falls der Extraktions-Prompt sich künftig ändert (z. B. neue Felder) - müsste bei einer Prompt-Änderung manuell nachgezogen werden.

**Erweiterungen:**
- `GET /suggestions` (T11) könnte im `cached`-Modus automatisch nur die 5 hier hinterlegten Fragen zeigen, im `live`-Modus freiere Vorschläge - noch nicht verdrahtet.

---

## T10 — Zahlenabgleich Formulierung vs. facts

**Stand:** Fertig — `services/verification_service.py`, live verifiziert an 7 Fällen: der historische T7-Bug (Einheiten-Verwechslung) reproduziert und bestätigt jetzt erkannt, ein korrekter Text besteht, eine erfundene Zahl wird erkannt, Rundungstoleranz greift korrekt nur bei 5y/10y, Hebel-Beträge werden korrekt akzeptiert, ein echter End-to-End-Test mit künstlich kaputt gemachtem LLM-Text zeigt den Fallback in Aktion, und ein Regressionstest über 5 echte LLM-Antworten zeigt 0 falsch-positive Ablehnungen.

**Bugs:** Keine gefunden.

**Design-Entscheidungen:**
- **Zahlen werden typgebunden geprüft, nicht als nackte Zahlenmenge.** Der Kern der ganzen Idee: eine mit "CHF" geschriebene Zahl wird nur gegen echte CHF-Werte aus `facts`/`levers` geprüft, eine mit "Monat(en)" geschriebene Zahl nur gegen echte Monats-Werte. Das ist genau die Lücke, die eine naive "kommt diese Zahl irgendwo in facts vor?"-Prüfung offen gelassen hätte - der historische Bug (`buffer_after_months=1.1` als "CHF 1" beschrieben) hätte eine untypisierte Prüfung nicht gefangen, weil die Zahl 1 (gerundet von 1.1) ja tatsächlich in `facts` vorkommt. Live mit genau diesem Fall bewiesen.
- **Fallback nutzt `template_answer()` (T9) wieder**, statt einen zweiten Fallback-Mechanismus zu bauen - eine Codebasis für "garantiert korrekter Text ohne LLM", die für zwei verschiedene Zwecke (Cache-Modus, Verifikations-Fallback) wiederverwendet wird.
- **Toleranz statt exakter Übereinstimmung**, weil das Rundungs-Vorgabe im Formulierungs-Prompt (auf 100 CHF bei 5y/10y) sonst ständig false positives ausgelöst hätte - 60 CHF Tolerenz bei 5y/10y (etwas mehr als die theoretischen ±50 einer Rundung-auf-100, um dem Modell etwas Spielraum bei der Rundungsrichtung zu lassen), 1 CHF bei present/1y (keine Rundung erlaubt, entsprechend strikt). Live verifiziert: dieselbe Abweichung wird bei 5y toleriert, bei present korrekt abgelehnt.
- **`source` bleibt `"live"` auch wenn der Fallback greift** - die Berechnung war live und echt, nur die Wortwahl kam vom Template statt vom Modell. Ein Logging-Warning (`logger.warning`) macht das für die QA/den Betrieb trotzdem sichtbar, ohne das Response-Schema um ein weiteres Feld zu erweitern.
- **Nur CHF- und Monats-Zahlen werden geprüft**, keine Handlungs-Beschreibung (z. B. ob "gekündigt" tatsächlich der richtige Fall ist) - das ist strukturell schon in T7 gelöst (`adjustment_description` gibt die Handlung fest vor, das Modell muss sie nicht mehr erraten), nicht nochmal Aufgabe des Zahlenabgleichs. "Zahlenabgleich" im Namen ist wörtlich zu nehmen.

**Grenzen:**
- Erkennt nur Zahlen, die explizit mit "CHF" oder "Monat(en)" geschrieben sind - eine Zahl ganz ohne Einheitswort (unwahrscheinlich bei den Prompt-Vorgaben, aber theoretisch möglich) würde nicht geprüft.
- Keine Prüfung, ob eine im Text genannte Zahl eine *korrekte Ableitung* aus mehreren `facts`-Werten ist (z. B. eine Summe aus zwei Beträgen) - nur ob sie *irgendeinem einzelnen* erwarteten Wert nahekommt. Für die bisher beobachteten Formulierungen (die immer einzelne `facts`-Felder direkt nennen, keine eigenen Summen bilden) ausreichend, aber keine allgemeine Arithmetik-Prüfung.
- Kein automatisiertes Eval-Set über viele Fragen - die 0-Falsch-Positive-Beobachtung stammt aus 5 Live-Calls in einem Testlauf, nicht aus einer grösseren Stichprobe.

**Erweiterungen:**
- Die gleiche typgebundene Prüfung liesse sich leicht auf weitere Einheiten ausweiten (z. B. Prozent-Angaben), falls künftige Antworttexte das brauchen.

---

## T11 — api/routes/assistant.py (beide Endpunkte)

**Stand:** Fertig — `POST /api/v1/assistant/ask` und `GET /api/v1/assistant/suggestions`, erstmals über echtes HTTP erreichbar (nicht mehr nur Python-Funktionsaufrufe wie in T3-T10). Live getestet: beide Endpunkte per `curl`, 422-Validierung, `unsupported`, kompletter Rückfrage-Flow über zwei echte HTTP-Requests mit persistentem Conversation-State, OpenAPI-Schema-Korrektheit (inkl. der Chart-Discriminated-Union), und — als härtester Beweis — ein komplett separater Container **ohne jeden `OPENAI_API_KEY`** im `cached`-Modus, der über echtes HTTP eine vollständige, korrekte Antwort liefert.

**Bugs:** Ein Infrastruktur-Fund (kein Code-Bug): Ein erster Test des `cached`-Containers per `docker run` schlug mit `404 Not Found` fehl - Ursache war ein **veraltetes Docker-Image**. Der Dev-Container läuft mit Live-Reload über ein gemountetes Volume, ein eigenständiger `docker run` nutzt aber das zuletzt mit `docker compose build` gebaute Image, das T11s neue Route noch nicht enthielt. Behoben durch `docker compose build api` vor dem Test - danach lief der Beweis sauber durch. Für die Doku festgehalten, damit das nicht als Verwirrung durchgeht, falls es nochmal auftritt.

**Design-Entscheidungen:**
- **REST-Contract wörtlich nach Issue**, wie zu Beginn des Features entschieden - eigener Router, nicht Teil von Feature 4s OData-Subset. Läuft trotzdem unter demselben `/api/v1`-Prefix wie Feature 4 (seit deiner Umstellung von `/odata`).
- **Fehler-Envelope wird von Feature 4 wiederverwendet, nicht neu erfunden.** `install_odata_error_handlers` (T9, Feature 4) ist service-weit in `main.py` installiert und fängt `HTTPException`/`RequestValidationError` service-weit ab - meine `HTTPException(...)`-Aufrufe hier kommen automatisch im selben `{"error": {"code","message"}}`-Format raus wie bei `/odata/...`. Bewusst genutzt statt eines zweiten Fehlerformats nur für diesen Router - ein konsistentes Format über die ganze API ist besser als zwei.
- **Timeout/LLM-Fehler werden zu 504/502**, nicht generisch 500 - nutzt `AssistantLLMTimeoutError.stage` (T9) für eine präzise Meldung, welcher der beiden LLM-Calls betroffen war.
- **`GET /suggestions`** liefert bewusst natürliche, pro Horizont variierte Vorschläge statt stur alle 5 T9-Cache-Fragen zu wörtlich zu spiegeln - die meisten Einträge SIND live-verifizierte Cache-Treffer, aber `suggestions` ist als allgemeiner UX-Helfer für den `live`-Modus gedacht, nicht als Cache-Vertrag. Ein nicht-gecachter Chip-Klick im `cached`-Modus degradiert sauber (listet die echten 5 Fragen, siehe T9), stürzt nicht ab.

**Grenzen:**
- Der 409-Pfad ("Kein Saldo vorhanden") wurde hier nicht eigenständig über echtes HTTP erneut getriggert - `AssistantAskRequest` hat bewusst kein `as_of`-Feld (Issue-Contract), daher lässt sich der Fall über die öffentliche API praktisch nicht natürlich auslösen. Der Route-Code ist aber identisch zum bereits ausführlich getesteten Feature-4-Muster (`app/api/routes/forecast.py::_no_balance_error`), verlässt sich auf dessen Testabdeckung.
- Keine Rate-Begrenzung oder Request-Grössenbeschränkung über Pydantic hinaus (schon vorhanden: `message` max. 1000 Zeichen, T1) - für eine Hackathon-Demo ausreichend.

**Erweiterungen:**
- `GET /suggestions` könnte künftig `ASSISTANT_MODE` selbst abfragen und im `cached`-Modus automatisch nur die 5 garantiert funktionierenden Fragen zeigen (in T9 als Idee vorgemerkt) - aktuell macht das niemand automatisch, ein Frontend müsste das selbst wissen oder den Nutzer im `cached`-Fall entsprechend hinweisen.
