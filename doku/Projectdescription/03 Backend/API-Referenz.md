---
tags: [backend, api]
---

# API-Referenz

Vollreferenz: `apps/api/API.md` · interaktiv: Swagger unter `http://localhost:8000/docs` · CSDL: `GET /api/v1/$metadata` · Technik dahinter: [[OData-Layer]]

Mount-Pfad `/api/v1` (vormals `/odata`) — reine Pfad-Umbenennung, konsistent mit dem [[Future-Me Chatbot]]s `/api/v1/assistant/...`; die OData-Semantik (Envelope, Header, `$metadata`, Fehlerformat) bleibt unverändert.

## Endpunkte

| Endpunkt                   | HTTP | OData-Konzept | Zweck                                                                      | Code                              |
| -------------------------- | ---- | ------------- | -------------------------------------------------------------------------- | --------------------------------- |
| `/api/v1/RecurringPayments` | GET  | EntitySet     | Erkannte wiederkehrende Zahlungen, volle Query-Optionen                    | `app/api/routes/forecast.py`      |
| `/api/v1/GetForecast`       | GET  | Function      | Basisprognose (`horizon`, `as_of`)                                         | `app/api/routes/forecast.py`      |
| `/api/v1/Simulate`          | POST | Action        | Prognose mit Eingriffen: Baseline + Szenario + Diff in einer Antwort       | `app/api/routes/forecast.py`      |
| `/api/v1/GetSubscriptions`  | GET  | Function      | Komplette [[Abo-Radar]]-Payload in einem Request *(uncommitted)*           | `app/api/routes/subscriptions.py` |
| `/health`                  | GET  | —             | Ausführlicher Smoke-Test (Zeilenzahlen, Lohntag, Töpfe, Beispiel-Prognose) | `app/main.py`                     |

## `RecurringPayments` — Querying

`$filter`, `$select`, `$orderby`, `$top`, `$skip`, `$count`. `$filter`-Grammatik (handgeschrieben, [[OData-Layer]]): `eq ne gt ge lt le`, `and/or/not`, Klammern, String/Zahl/Bool/Null-Literale — kein `contains`/`startswith`.

```bash
curl "http://localhost:8000/api/v1/RecurringPayments?\$filter=is_active%20eq%20true&\$orderby=amount_chf%20desc&\$top=5&\$count=true"
```

Zwei Besonderheiten:
- **`recurring_id`** ist die zusammengesetzte ID `merchant::category_main::flow` (z. B. `"NETFLIX.COM::Wohnen::expense"`) — Merchant-Strings allein sind nicht eindeutig ([[Glossar]]).
- **`amount_history` ist per Default ausgeklammert** (war 88 % der Payload); explizit per `$select=merchant,amount_history` abrufbar. Der Endpunkt hat bewusst kein festes `response_model`, weil `$select` beliebige Subsets projiziert.

## `GetForecast`

Parameter `horizon` (`next_salary` | `30d` | `90d` | `365d`, Default `next_salary`) und `as_of` (Default heute, für Demos fixierbar). Antwort (`ForecastEnvelope`): `opening_balance_chf`, `next_salary`, `free_to_spend` (expected/lower/upper), `tight_date` (oder `null`), `known_payments`, `series` (kumulierte Saldokurve mit Band), `assumptions`. **409** mit OData-Error, wenn für `as_of` kein Saldo verfügbar ist → Frontend soll ein Startsaldo-Eingabefeld zeigen.

## `Simulate`

```json
{ "horizon": "365d", "adjustments": [ {"type": "cancel_recurring", "recurring_id": "NETFLIX.COM::Wohnen::expense"} ] }
```

Vier kombinierbare Eingriffstypen (Discriminator `type`): `cancel_recurring` (optional `effective_from`), `adjust_recurring` (`delta_chf`), `add_recurring` (`label`, `amount_chf`, `interval`, `start_date`), `one_off` (`amount_chf` immer **positive Ausgaben-Magnitude**). Antwort: `baseline` + `scenario` (je wie `GetForecast`) + `diff` (`monthly_chf`, `cumulative_series`, `total_at_horizon_chf`, `tight_date_shift_days`) — Vorzeichen durchgehend **positiv = besser**. Mechanik: [[Forecast-Service]].

## `assumptions` — "Woher kommen diese Zahlen?"

Jede Prognose-Antwort trägt `variable_baseline_method` (`median_6m`), `band_method` (`p25_p75`), `excluded_outliers` (benannte Ausreisser), `interest_applied` (immer `false`), `salary_day_detected` und freitextige `notes` für Edge-Cases ("Lohntag nicht erkennbar – Fallback auf Kalendermonat").

## Fehlerformat

Alle Fehler im OData-v4-Format `{"error": {"code", "message"}}` statt FastAPIs `{"detail": ...}`; 422-Validierungsfehler zusätzlich mit `details` und Feld-Pfaden.
