---
tags: [feature]
status: offen
issue: 8
---

# Alerts

Spec: [[Issue 8 – Alerts]] · baut auf der Klassifikation aus [[Issue 4 – Zukunftsprognose]] auf (`outlier`-Topf, `monthly_category_stats`, `group_key`)

## Die Idee

**Niemand liest 5'000 Buchungen.** Die Seite «Auffälligkeiten» hebt die wenigen Ereignisse hervor, die einen Blick wert sind — doppelte Abbuchungen, ungewöhnlich grosse Zahlungen, Ausgaben-Spitzen in einer Kategorie — damit der User nicht jede Transaktion einzeln durchgehen muss. Bewusst eine eigene View: Alerts sind eine priorisierte Liste, kein Filter über der Transaktionstabelle.

Leitsatz wie beim [[Abo-Radar]]: **Fehlalarme kosten Vertrauen.** Alle Schwellen sind konservativ gewählt, jeder Alert-Typ hat dokumentierte Guards gegen bekannte False-Positive-Quellen, und Negativ-Tests sind Teil der Definition of Done.

## Die drei Alert-Typen

| Typ | Severity | Regel |
|---|---|---|
| `duplicate_charge` | danger | Gleicher Händler, gleicher Betrag, gleicher Tag, ≥ 2 Buchungen, Betrag ≥ CHF 20. Läuft auf den rohen, **nicht** same-day-kollabierten Transaktionen; Händler-Kanonisierung via bestehendem `group_key` aus `recurring_detection.py`. Byte-identische CSV-Zeilen zählen bewusst mit — der Export ist nicht dedupliziert, und «ist das zweimal abgebucht?» ist genau die Frage, die der Alert dem User stellt. |
| `large_payment` | warning | Wiederverwendung der Outlier-Klassifikation (`classification.py`: > 3× Kategorie-Median **und** ≥ CHF 100), zusätzlich absoluter Floor CHF 100 auch für den Selten-Kategorie-Zweig — ein CHF-12-Kauf in einer seltenen Kategorie darf nicht alerten. `baseline_chf` = Kategorie-Median. |
| `category_spike` | info | Monatssumme einer Kategorie ≥ 2.0× des 6-Monats-Medians **und** Delta ≥ CHF 150. Nur über `topf == "variable"`-Buchungen: Fixkosten ausgeschlossen (keine Miet-«Spikes»), Outlier ausgeschlossen (eine grosse Zahlung wird nicht doppelt geflaggt als Typ 2 *und* Typ 3). Baseline via bestehendem `monthly_category_stats`, mindestens 3 Monate Historie. Der aktuelle Teilmonat wird mit derselben Regel mitgeprüft — er kann nur unter-triggern, nie falsch alarmieren. |

**Gemeinsame Guards:** nur `flow == "expense"` (Einkommen alertet nie); interne Umbuchungen per Kategorie ausgeschlossen (`Sonstige Geldtransfers`, `Überträge` — `is_transfer` ist unimplementiert, die Kategorie ist der Proxy). Schwellen als env-überschreibbare Konstanten im Stil der `OUTLIER_*`-Werte: `ALERT_DUPLICATE_MIN_CHF=20`, `ALERT_SPIKE_MULTIPLIER=2.0`, `ALERT_SPIKE_MIN_DELTA_CHF=150`, `ALERT_SPIKE_MIN_MONTHS=3`.

## API

OData-EntitySet **`GET /odata/Alerts`** — bewusst EntitySet statt Function: eine parameterlose, deterministische Collection wie `RecurringPayments`, damit `$filter`/`$orderby`/`$top`/`$count` gratis über `apply_query_options` funktionieren. Berechnung einmal im `lifespan`, abgelegt als `app.state.alerts`.

Das Schema ist sprach-neutral (Enums, keine deutschen Sätze — die rendert das Frontend, konsistent mit allen bestehenden Endpoints, und `$filter=type eq 'duplicate_charge'` bleibt sauber):

```
alert_id       stabiler Slug, z. B. "dup:2026-03-14:migros:45.90", "spike:2026-03:freizeit:reisen"
type           duplicate_charge | large_payment | category_spike
severity       danger | warning | info   (feste Zuordnung pro Typ)
date           Datum des Vorfalls (Spike: letzte Buchung der Kategorie im Monat)
month          "YYYY-MM", nur bei Spikes
merchant       null bei Spikes
category_main / category_sub
amount_chf     positiver Betrag (Duplikat: Einzelbuchung; Spike: Monatssumme)
baseline_chf   Kategorie-Median (large) bzw. Monats-Median (spike)
count          Gruppengrösse bei Duplikaten
booking_text   erster Avisierungstext — Transaktionen haben keine IDs, das ist die Referenz
```

## Frontend-Seite

Route `/alerts`, Titel und Nav-Label **«Auffälligkeiten»** — weniger alarmistisch als «Warnungen» (Typ 3 ist info-Grad, kein Alarm) und passt zur Domänensprache («Ausreisser»).

Aufbau: Kopfzeile mit drei KPI-Kacheln (Counts pro Severity), Filterzeile (Typ, Schweregrad), darunter die Kartenliste datum-absteigend. Pro Karte: Icon je Typ, deutscher Titel plus ein **«Warum sehe ich das?»-Satz** aus dem Enum gerendert — z. B. *«2× derselbe Betrag (CHF 45.90) bei Migros am 14.03. – möglicherweise doppelt belastet.»* Severity-Akzent über die danger/warning-Farbtokens, `booking_text` als Kleintext. Empty-State: *«Keine Auffälligkeiten gefunden.»* mit beruhigender Unterzeile.

Service `core/alerts.ts` mit `httpResource`, nach dem Muster von `core/forecast.ts` auf `feature/prognosis`.

## Wiederverwendung (nicht neu bauen)

`classify_transactions`/`outlier` und die `OUTLIER_*`-Schwellen (`classification.py`), `monthly_category_stats` (`transaction_repository.py`), `group_key` (`recurring_detection.py`), `apply_query_options`/`odata_collection` (OData-Layer), Route-Pattern aus `forecast.py`.

## Status

Noch nicht begonnen — dieses Dokument ist die Definition. Geplante Umsetzung auf einem Branch ab `main`; die Frontend-Infrastruktur (HttpClient-Provider, `proxy.conf.json`, danger/warning-Tokens) wird von `feature/prognosis` portiert. Details und offene Fragen: [[Issue 8 – Alerts]].
