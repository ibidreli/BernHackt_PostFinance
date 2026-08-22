# API-Dokumentation: Zukunftsprognose & Szenario-Simulation

Diese Datei ist die kompakte Referenz für die drei Endpunkte. Für Details zu Bugs, Grenzen und Design-Entscheidungen siehe [STATUS.md](STATUS.md) — dort steht auch, *warum* bestimmte Dinge so gebaut sind, wie sie sind.

## Grundlagen

- **Keine Datenbank.** Die Bank-Export-CSV ist die einzige Datenquelle, beim Start einmal in den Speicher geladen. Kein Persistenz-Layer, keine Migration.
- **OData v4, pragmatisches Subset.** `OData-Version: 4.0`-Header auf jeder Antwort, `@odata.context`-Envelope, OData-JSON-Error-Format (`{"error": {"code", "message"}}`). Kein `$batch`, keine Atom/XML-Repräsentation. Details: [STATUS.md, T9](STATUS.md#t9--odata-layer).
- **Kein Zins, keine Rendite.** `assumptions.interest_applied` ist immer `false`. Die Hochrechnung ist reine Summierung.
- **Interaktiv testen:** `/docs` (Swagger UI) nach `docker compose up` — siehe [README.md](../../README.md) für Run-Anleitung.
- **CSDL-Dokument:** `GET /odata/$metadata`.

## Die drei Endpunkte

| Endpunkt | HTTP | OData-Konzept | Zweck |
|---|---|---|---|
| `/odata/RecurringPayments` | GET | EntitySet | Liste erkannter wiederkehrender Zahlungen, mit vollen Query-Optionen |
| `/odata/GetForecast` | GET | Function | Basisprognose ohne Szenario |
| `/odata/Simulate` | POST | Action | Prognose mit Eingriffen, Baseline + Szenario in einer Antwort |

---

### `GET /odata/RecurringPayments`

Query-Optionen: `$filter`, `$select`, `$orderby`, `$top`, `$skip`, `$count`.

```bash
curl "http://localhost:8000/odata/RecurringPayments?\$filter=is_active%20eq%20true&\$orderby=amount_chf%20desc&\$top=5&\$count=true"
```

**`$filter`-Grammatik** (handgeschrieben, kein vollständiges OData-ABNF — siehe `app/odata/query.py`):

- Operatoren: `eq`, `ne`, `gt`, `ge`, `lt`, `le`, kombinierbar mit `and`, `or`, `not`, Klammern
- Literale: `'string'`, Zahl, `true`/`false`, `null`
- Beispiele: `is_active eq true`, `flow eq 'expense'`, `amount_chf gt 100`, `not (is_active eq true)`

**Wichtig:** `recurring_id` ist **nicht** der Merchant-Name, sondern eine zusammengesetzte ID (`merchant::category_main::flow`), z. B. `"NETFLIX.COM::Wohnen::expense"`. Grund: Merchant-Strings sind nicht eindeutig (siehe STATUS.md, T7 — "LASTSCHRIFT", "PAYPAL" u. a. stehen für mehrere unabhängige Zahlungen). Diese ID wird für `cancel_recurring`/`adjust_recurring` gebraucht.

`$select` projiziert auf ein Feld-Subset — die Response hat dann kein festes Schema mehr, deshalb ist dieser Endpunkt in Swagger bewusst nicht strikt typisiert (im Gegensatz zu den anderen beiden).

**`amount_history` ist standardmässig ausgeklammert** (ohne explizites `$select`), da es bei manchen Merchants sehr lang wird — gemessen: 88 % der Payload einer 10-Item-Liste war `amount_history` eines einzelnen Merchants mit 196 Verlaufseinträgen. Explizit abrufbar per `$select=merchant,amount_history`.

---

### `GET /odata/GetForecast`

| Parameter | Typ | Default |
|---|---|---|
| `horizon` | `next_salary` \| `30d` \| `90d` \| `365d` | `next_salary` |
| `as_of` | Datum | heute |

```bash
curl "http://localhost:8000/odata/GetForecast?horizon=90d&as_of=2026-08-22"
```

Antwort folgt exakt dem Issue-Contract (`as_of`, `horizon_end`, `opening_balance_chf`, `next_salary`, `free_to_spend`, `tight_date`, `known_payments`, `series`, `assumptions`) plus `@odata.context`. Volles Schema in Swagger (`ForecastEnvelope`).

**`tight_date`** ist `null`, wenn der Puffer im Horizont nicht unterschritten wird — das Frontend zeigt dann den tiefsten Punkt aus `series` selbst, es gibt kein separates Feld dafür.

**Fehlerfall:** `409` mit OData-Error-Envelope, wenn für `as_of` kein Saldo verfügbar ist (Issue-Edge-Case "Kein Saldo vorhanden") — Frontend sollte dann ein Eingabefeld für den Startsaldo zeigen.

---

### `POST /odata/Simulate`

```bash
curl -X POST "http://localhost:8000/odata/Simulate" \
  -H "Content-Type: application/json" \
  -d '{
    "horizon": "365d",
    "adjustments": [
      {"type": "cancel_recurring", "recurring_id": "NETFLIX.COM::Wohnen::expense"}
    ]
  }'
```

**Die vier Eingriffstypen** (kombinierbar, siehe `type`-Feld als Discriminator):

| `type` | Felder | Preset |
|---|---|---|
| `cancel_recurring` | `recurring_id`, `effective_from?` | Netflix kündigen |
| `adjust_recurring` | `recurring_id`, `delta_chf` | Miete +200 |
| `add_recurring` | `label`, `amount_chf`, `interval`, `start_date` | — |
| `one_off` | `label`, `amount_chf`, `date` | — (Feature 3: "Auto für 30'000?") |

`amount_chf` ist bei `one_off` immer eine **positive Ausgaben-Magnitude** — kein Vorzeichen-Trick für Einnahmen (gefundener Bug, siehe STATUS.md T7).

**"Kantine halbieren" ist bewusst nicht abbildbar** — keiner der vier Typen erlaubt eine Topf-2-Kategorie-Anpassung, das wurde mit dem Team so bestätigt (siehe STATUS.md T7).

**`diff`-Vorzeichen-Konvention:** durchgehend `scenario - baseline`, **positiv = besser** (mehr Saldo, mehr Puffer-Tage). Das weicht bewusst vom mehrdeutigen Beispiel in der ursprünglichen Issue-JSON ab — Begründung in STATUS.md, T7.

---

## `assumptions` — die Antwort auf "woher kommen diese Zahlen?"

```json
{
  "variable_baseline_method": "median_6m",
  "band_method": "p25_p75",
  "excluded_outliers": ["RENNVELO", "STEUERVERWALTUNG DES KT. BERN ..."],
  "interest_applied": false,
  "salary_day_detected": true,
  "variable_baseline_months_used": 6,
  "notes": []
}
```

`notes` ist eine Erweiterung über den Issue-Contract hinaus: freitextige Hinweise statt eines Booleans pro Edge-Case (z. B. `"Lohntag nicht erkennbar - Fallback auf Kalendermonat."`). Deckt die Issue-Edge-Cases ab, ohne das Schema für jeden neuen Fall zu erweitern.

## Fehlerformat

Alle Fehler folgen dem OData-v4-Format statt FastAPIs Standard `{"detail": ...}`:

```json
{ "error": { "code": "404", "message": "Not Found" } }
```

Validierungsfehler (422) enthalten zusätzlich `details` mit Feld-Pfaden.

## Bekannte Grenzen, kurz

Vollständige Liste mit Begründung in [STATUS.md](STATUS.md). Die wichtigsten:

- `$filter` deckt kein `contains`/`startswith` ab.
- `$metadata` ist statisch, nicht aus den Schemas generiert.
- `GetForecast` nutzt Query-Parameter statt strikter OData-Klammer-Syntax (`GetForecast(horizon='...')`).
- Band wächst linear über die Zeit, nicht mit gedämpfter Zeitskalierung.

---

# Assistenz (`/api/v1/assistant`)

Plain REST, nicht OData: die beiden Endpunkte sind kein Entity-Set und keine
typisierte Funktion über dem Datenmodell, sondern eine konversationelle Operation.

## `POST /api/v1/assistant/ask`

Beantwortet genau drei Fragetypen. Alles andere → `status: "unsupported"`, ohne
Rateversuch.

| `intent`        | Frage                                       | Chart-Typ           |
| --------------- | ------------------------------------------- | ------------------- |
| `affordability` | "Kann ich mir ein Auto für 30'000 leisten?"  | `wealth_over_time`  |
| `what_if`       | "Was wäre, wenn ich Gastronomie halbiere?"   | `before_after`      |
| `time_to_goal`  | "Wann habe ich 20'000 zusammen?"             | `goal_progress`     |

`status` ist nie ein blosses Ja oder Nein: `yes` (Ziel erreichbar, Restpuffer
≥ 3 Monatsausgaben), `tight` (erreichbar, Puffer darunter, mit Wartezeit),
`no_unless` (Fehlbetrag, nötiger Monatsbetrag, Hebel) — dazu
`needs_clarification` und `unsupported`.

Horizonte: `present` (aktuelle Lohnperiode, die einzige Stufe ohne Annahmen —
die Kurve kommt direkt aus `GetForecast(horizon=next_salary)`), `1y`, `5y`, `10y`.
Ein Horizont im Fragetext schlägt den Umschalter; der tatsächlich verwendete
steht als `horizon` in der Antwort.

**Wo gerechnet wird.** Ausschliesslich in `forecast_service` — derselben Funktion,
die auch der Slider aus Feature 2 aufruft. `forecast_service` endet bei 365 Tagen;
für 5 und 10 Jahre extrapoliert `assistant_service` dessen Monatsraten unter den
drei sichtbaren Annahmen weiter (Formel im Modul-Docstring). Kein Zins, keine
Rendite: `assumptions_used.interest_applied` ist immer `false`.

**Wo nicht gerechnet wird.** Die Extraktion (`intent_service`) liefert nur
Parameter, die Formulierung baut den Text aus `facts` per Template. `_verify_numbers`
prüft danach, dass jeder CHF-Betrag im Text einem Feld aus `facts` oder `levers`
entspricht; bei Abweichung greift die neutrale Template-Formulierung. Die
äquivalenten LLM-Contracts liegen versioniert unter [`prompts/`](../../prompts/).

**Hebel** stammen ausschliesslich aus variablen Kategorien (Topf 2), abzüglich der
nicht disponiblen (`Steuern`, `Versicherungen`, `Sonstige Geldtransfers`) — "spar
bei der Krankenkasse" ist kein Rat. `potential_chf` ist pauschal 50 % der Kategorie.

**Rückfragen** sind fest definiert, nicht vom Modell erfunden, und maximal eine pro
Anfrage: fehlender Betrag, und Bar/Leasing ab CHF 10'000. Wird eine Rückfrage über
`context.pending_clarification` beantwortet, wird sie nicht erneut gestellt.

## `GET /api/v1/assistant/suggestions?horizon=5y`

Drei Vorschlagsfragen als Chips, abhängig vom Horizont.

## Bekannte Grenzen

- Extraktion ist regelbasiert (Regex), nicht LLM-gestützt — gleicher Contract,
  kein API-Key, kein Timeout in der Live-Demo. `prompts/` dokumentiert den
  LLM-Ersatz; `source` ist entsprechend `"template"`.
- Leasing vereinfacht: 20 % Anzahlung, Rest als monatliche Rate über den Horizont
  (in `assumptions_used.notes` benannt).
- Folgefragen mit Bezug auf die vorherige Antwort ("und wenn ich 2 Jahre länger
  warte?") sind nicht im Scope.
- Die `tight`-Schwelle von 3 Monatsausgaben ist ein Startwert, nicht kalibriert.
