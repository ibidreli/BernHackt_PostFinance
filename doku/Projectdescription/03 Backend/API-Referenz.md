---
tags: [backend, api]
---

# API-Referenz

Vollreferenz: `apps/api/API.md` · interaktiv: Swagger unter `http://localhost:8000/docs` · CSDL: `GET /api/v1/$metadata` · Technik dahinter: [[OData-Layer]]

Mount-Pfad `/api/v1` (vormals `/odata`, umbenannt mit Commit `24ba87e`) — reine Pfad-Umbenennung; die OData-Semantik (Envelope, Header, `$metadata`, Fehlerformat) bleibt unverändert. Ausnahme: der [[Future-Me Chatbot]] läuft als **REST** unter `/api/v1/assistant/*` (Issue-Contract wörtlich, eigene Referenz `apps/api/ASSISTANT_API.md`) — das Fehlerformat ist trotzdem dasselbe, weil die OData-Error-Middleware service-weit gilt. Der `OData-Version: 4.0`-Header liegt seit dem 22.08. **nur noch auf den OData-Routen** (`/$metadata`, `/Alerts`, `/RecurringPayments`, `/GetForecast`, `/Simulate`) — nicht mehr auf `/health`, `/graph*` und `/assistant/*`.

## Endpunkte

| Endpunkt                   | HTTP | OData-Konzept | Zweck                                                                      | Code                              |
| -------------------------- | ---- | ------------- | -------------------------------------------------------------------------- | --------------------------------- |
| `/api/v1/RecurringPayments` | GET  | EntitySet     | Erkannte wiederkehrende Zahlungen, volle Query-Optionen                    | `app/api/routes/forecast.py`      |
| `/api/v1/Alerts`            | GET  | EntitySet     | [[Alerts]]: Duplikate, grosse Zahlungen, Kategorie-Spikes — konsumiert von Kategorien- **und** Prognose-Seite | `app/api/routes/alerts.py`        |
| `/api/v1/GetForecast`       | GET  | Function      | Basisprognose (`horizon`, `as_of`)                                         | `app/api/routes/forecast.py`      |
| `/api/v1/Simulate`          | POST | Action        | Prognose mit Eingriffen: Baseline + Szenario + Diff in einer Antwort       | `app/api/routes/forecast.py`      |
| `/api/v1/assistant/ask`     | POST | — (REST)      | [[Future-Me Chatbot]]: Frage in natürlicher Sprache → Antwort mit Facts/Hebeln/Chart (Referenz: `apps/api/ASSISTANT_API.md`) | `app/api/routes/assistant.py` |
| `/api/v1/assistant/suggestions` | GET | — (REST)    | Drei Vorschlagsfragen-Chips pro Horizont                                   | `app/api/routes/assistant.py`     |
| `/api/v1/graph`(`/months`)  | GET  | — (REST)      | [[Kategorien-Explorer]]: kompletter Baum mit Inline-Transaktionen; Consumer ist die Explorer-Seite | `app/api/routes/graph.py`        |
| `/health`                  | GET  | —             | Ausführlicher Smoke-Test (Zeilenzahlen, Lohntag, Töpfe, Beispiel-Prognose) | `app/main.py`                     |

Die frühere OData-Graph-Variante (`GraphNodes`/`GraphMonths`, `graph_odata.py`) wurde am 22.08. samt CSDL-Einträgen **entfernt** — der Explorer nutzt die REST-Variante. `GetSubscriptions` ([[Abo-Radar]]) wurde nie gebaut und ist mit dem Streichen des Features vom Tisch.

## `RecurringPayments` & `Alerts` — Querying

`$filter`, `$select`, `$orderby`, `$top`, `$skip`, `$count`. `$filter`-Grammatik (handgeschrieben, [[OData-Layer]]): `eq ne gt ge lt le`, `and/or/not`, Klammern, String/Zahl/Bool/Null-Literale — kein `contains`/`startswith`. **Unbekannte Felder in `$filter`/`$select`/`$orderby` liefern seit dem 22.08. einen `400` mit OData-Error** — vorher kamen stille `null`-Spalten bzw. leere Listen zurück.

```bash
curl "http://localhost:8000/api/v1/RecurringPayments?\$filter=is_active%20eq%20true&\$orderby=amount_chf%20desc&\$top=5&\$count=true"
```

Zwei Besonderheiten:
- **`recurring_id`** ist die zusammengesetzte ID `merchant::category_main::flow` (z. B. `"NETFLIX.COM::Wohnen::expense"`) — Merchant-Strings allein sind nicht eindeutig ([[Glossar]]).
- **`amount_history` ist per Default ausgeklammert** (war 88 % der Payload); explizit per `$select=merchant,amount_history` abrufbar. Der Endpunkt hat bewusst kein festes `response_model`, weil `$select` beliebige Subsets projiziert.

`Alerts` liefert die beim Startup deterministisch berechneten Auffälligkeiten (Typen, Schwellen, Guards: [[Alerts]]); `transaction_id`/`transaction_ids` (`tx-*`) sind die Basis für die Deep-Links des Frontends. Konsumiert wird die Liste von beiden Seiten über einen einzigen Fetch in `core/alerts.ts` (client-seitiger Join).

## `GetForecast`

Parameter `horizon` (`next_salary` | `30d` | `90d` | `365d`, Default `next_salary`) und `as_of` (Default heute, für Demos fixierbar). Antwort (`ForecastEnvelope`): `opening_balance_chf`, `next_salary`, `free_to_spend` (expected/lower/upper), `tight_date` (oder `null`), `known_payments`, `series` (kumulierte Saldokurve mit Band), `assumptions`. **409** mit OData-Error, wenn für `as_of` kein Saldo verfügbar ist → Frontend soll ein Startsaldo-Eingabefeld zeigen.

## `Simulate`

```json
{ "horizon": "365d", "adjustments": [ {"type": "cancel_recurring", "recurring_id": "NETFLIX.COM::Wohnen::expense"} ] }
```

Fünf kombinierbare Eingriffstypen (Discriminator `type`): `cancel_recurring` (optional `effective_from`), `adjust_recurring` (`delta_chf`), `add_recurring` (`label`, `amount_chf`, `interval`, `start_date`), `one_off` (`amount_chf` immer **positive Ausgaben-Magnitude**) und — neu seit dem 22.08. — **`adjust_category`**: `category_main`, optional `category_sub` (`null` = ganze Hauptkategorie), genau eines von `percent` (≥ −100) oder `delta_chf`, optional `effective_from`. Skaliert Median/P25/P75 der getroffenen Kategorien in der variablen Baseline (Band skaliert mit); `delta_chf` wird proportional auf die getroffenen Subkategorien verteilt; unbekannte Kategorie = stilles No-op (wie eine vertippte `recurring_id`). Antwort: `baseline` + `scenario` (je wie `GetForecast`) + `diff` (`monthly_chf`, `cumulative_series`, `total_at_horizon_chf`, `tight_date_shift_days`) — Vorzeichen durchgehend **positiv = besser**. Mechanik: [[Forecast-Service]].

## `assistant/ask` — `intervention` bei `what_if`

`what_if`-Antworten des [[Future-Me Chatbot|Assistenten]] tragen seit dem 22.08. zusätzlich ein maschinenlesbares Feld **`intervention`** — das aufgelöste Adjustment (z. B. der `adjust_category`-Eingriff hinter "Gastronomie halbieren"). Das Frontend nutzt es für "Als Szenario in Prognose übernehmen". Details: `apps/api/ASSISTANT_API.md`.

## `assumptions` — "Woher kommen diese Zahlen?"

Jede Prognose-Antwort trägt `variable_baseline_method` (`median_6m`), `band_method` (`p25_p75`), `excluded_outliers` (benannte Ausreisser), `interest_applied` (immer `false`), `salary_day_detected` und freitextige `notes` für Edge-Cases ("Lohntag nicht erkennbar – Fallback auf Kalendermonat").

## Fehlerformat

Alle Fehler im OData-v4-Format `{"error": {"code", "message"}}` statt FastAPIs `{"detail": ...}`; 422-Validierungsfehler zusätzlich mit `details` und Feld-Pfaden.
