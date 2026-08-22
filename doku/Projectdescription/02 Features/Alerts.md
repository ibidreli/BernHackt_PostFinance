---
tags: [feature]
status: umgesetzt
issue: 8
---

# Alerts

Spec: [[Issue 8 – Alerts]] · baut auf der Klassifikation aus [[Issue 4 – Zukunftsprognose]] auf (`outlier`-Topf, `monthly_category_stats`, `group_key`)

> [!important] Soll-Änderung (22.08.2026, [[Sollstatus]]): keine eigene Seite — **so umgesetzt**
> Die drei Alert-Typen, Guards und das Backend-Schema unten bleiben gültig (die **Schwellen wurden bei der Umsetzung rekalibriert**, siehe Tabelle). **Gestrichen ist nur die eigene Frontend-Seite** (Route `/alerts`, KPI-Kacheln, Kartenliste): Alerts erscheinen dort, wo die Daten sichtbar sind — als Severity-Ringe/Badges an Knoten im [[Kategorien-Explorer]] (inkl. Filter "Nur Auffälligkeiten" und "Warum sehe ich das?"-Satz im Detailpanel) und als Auffälligkeiten-Liste/Warn-Marker in der Prognose. Der Abschnitt "Frontend-Seite" unten ist damit überholt.

## Die Idee

**Niemand liest 5'000 Buchungen.** Die Seite «Auffälligkeiten» hebt die wenigen Ereignisse hervor, die einen Blick wert sind — doppelte Abbuchungen, ungewöhnlich grosse Zahlungen, Ausgaben-Spitzen in einer Kategorie — damit der User nicht jede Transaktion einzeln durchgehen muss. Bewusst eine eigene View: Alerts sind eine priorisierte Liste, kein Filter über der Transaktionstabelle.

Leitsatz wie beim [[Abo-Radar]]: **Fehlalarme kosten Vertrauen.** Alle Schwellen sind konservativ gewählt, jeder Alert-Typ hat dokumentierte Guards gegen bekannte False-Positive-Quellen, und Negativ-Tests sind Teil der Definition of Done.

## Die drei Alert-Typen

| Typ | Severity | Regel |
|---|---|---|
| `duplicate_charge` | danger | Gleicher Händler, gleicher Betrag, gleicher Tag, ≥ 2 Buchungen, Betrag ≥ CHF 20. Läuft auf den rohen, **nicht** same-day-kollabierten Transaktionen; Händler-Kanonisierung via bestehendem `group_key` aus `recurring_detection.py`. Byte-identische CSV-Zeilen zählen bewusst mit — der Export ist nicht dedupliziert, und «ist das zweimal abgebucht?» ist genau die Frage, die der Alert dem User stellt. |
| `large_payment` | warning | Wiederverwendung der Outlier-Klassifikation (`classification.py`), zusätzlich absoluter Floor **CHF 200** (rekalibriert; Spec sagte 100) auch für den Selten-Kategorie-Zweig — ein CHF-12-Kauf in einer seltenen Kategorie darf nicht alerten. `baseline_chf` = Kategorie-Median. |
| `category_spike` | info | Monatssumme einer Kategorie ≥ **2.5×** des 6-Monats-Medians **und** Delta ≥ **CHF 250** (rekalibriert; Spec sagte 2.0× / 150). Nur über `topf == "variable"`-Buchungen: Fixkosten ausgeschlossen (keine Miet-«Spikes»), Outlier ausgeschlossen (eine grosse Zahlung wird nicht doppelt geflaggt als Typ 2 *und* Typ 3). Baseline via bestehendem `monthly_category_stats`, mindestens **4 Monate** Historie (Spec: 3). Der aktuelle Teilmonat wird mit derselben Regel mitgeprüft — er kann nur unter-triggern, nie falsch alarmieren. |

**Gemeinsame Guards:** nur `flow == "expense"` (Einkommen alertet nie); interne Umbuchungen per Kategorie ausgeschlossen (`Sonstige Geldtransfers`, `Überträge` — `is_transfer` ist unimplementiert, die Kategorie ist der Proxy). Schwellen als env-überschreibbare Konstanten in `app/core/config.py`, im ausgelieferten Stand (PR #15, gegen die echten Daten kalibriert — teils strenger als die Spec): `ALERT_DUPLICATE_MIN_CHF=20`, `ALERT_LARGE_PAYMENT_MIN_CHF=200`, `ALERT_SPIKE_MULTIPLIER=2.5`, `ALERT_SPIKE_MIN_DELTA_CHF=250`, `ALERT_SPIKE_MIN_MONTHS=4`, dazu `ALERT_LOOKBACK_MONTHS=12` (Lookback-Fenster; `0` deaktiviert den Filter).

## API

OData-EntitySet **`GET /api/v1/Alerts`** — bewusst EntitySet statt Function: eine parameterlose, deterministische Collection wie `RecurringPayments`, damit `$filter`/`$orderby`/`$top`/`$count` gratis über `apply_query_options` funktionieren. Berechnung einmal im `lifespan`, abgelegt als `app.state.alerts`.

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
booking_text   erster Avisierungstext
transaction_id / transaction_ids   über die Spec hinaus: primäre Transaction.id ("tx-*")
               bzw. alle betroffenen IDs — Grundlage der Deep-Links ins Frontend
```

**Verknüpfung mit dem Graphen — client-seitiger Join:** Die Graph-Response trägt bewusst **kein** `alert_ids`-Feld; das Frontend (`core/alerts.ts`) holt `/api/v1/Alerts` einmal und joint selbst — die "einfachster Start"-Option aus dem [[Sollstatus]]. Transaktions-Blätter matchen per ID (`tx-*`), Merchants aggregieren die Alerts ihrer Transaktionen, Kategorie-Knoten tragen den `category_spike` des Monats (Match über die Kategorie-Felder).

## Frontend-Seite *(überholt — siehe Callout oben, nicht gebaut)*

Route `/alerts`, Titel und Nav-Label **«Auffälligkeiten»** — weniger alarmistisch als «Warnungen» (Typ 3 ist info-Grad, kein Alarm) und passt zur Domänensprache («Ausreisser»).

Aufbau: Kopfzeile mit drei KPI-Kacheln (Counts pro Severity), Filterzeile (Typ, Schweregrad), darunter die Kartenliste datum-absteigend. Pro Karte: Icon je Typ, deutscher Titel plus ein **«Warum sehe ich das?»-Satz** aus dem Enum gerendert — z. B. *«2× derselbe Betrag (CHF 45.90) bei Migros am 14.03. – möglicherweise doppelt belastet.»* Severity-Akzent über die danger/warning-Farbtokens, `booking_text` als Kleintext. Empty-State: *«Keine Auffälligkeiten gefunden.»* mit beruhigender Unterzeile.

Service `core/alerts.ts` mit `httpResource`, nach dem Muster von `core/forecast.ts` auf `feature/prognosis`.

## Wiederverwendung (nicht neu bauen)

`classify_transactions`/`outlier` und die `OUTLIER_*`-Schwellen (`classification.py`), `monthly_category_stats` (`transaction_repository.py`), `group_key` (`recurring_detection.py`), `apply_query_options`/`odata_collection` (OData-Layer), Route-Pattern aus `forecast.py`.

## Status

**Umgesetzt.** Backend in **PR #15** auf `main` (`app/services/alert_service.py`, `app/schemas/alert.py`, `GET /api/v1/Alerts`; getestet in `tests/test_alert_service.py` + `tests/test_alerts_route.py`). Frontend am 22.08. integriert — statt eigener Seite:

- **[[Kategorien-Explorer]]** (`/kategorien`): Severity-Ringe um betroffene Kreise (danger = rot, warning = amber, info = gestrichelter Teal-Ring), während des Slider-Scrubbens ausgeblendet (ein Alert gehört zu einem Monat); Filter-Chip **"Nur Auffälligkeiten"** mit Zähler, der nicht betroffene Kreise dimmt (kein Re-Packing — das Layout bleibt stabil); "Warum sehe ich das?"-Sätze im Rail des fokussierten Knotens und im Transaktions-Detailpanel.
- **Prognose** (`/`): **"Auffälligkeiten"-Liste** (letzte 3 Datenmonate, schwerste Severity zuerst, max. 6) — jede Zeile deep-linkt auf die passende Blase in `/kategorien`; in der Fixkosten-Liste tragen Zeilen mit aktuellem `large_payment`-Alert einen Warn-Punkt; ein `tight_date` mit gleichzeitigem `category_spike` zeigt einen "Treiber ansehen"-Link zur Spike-Kategorie.

Basis dafür ist `core/alerts.ts` mit dem oben beschriebenen client-seitigen Join. Historie und Schwellen-Diskussion: [[Issue 8 – Alerts]].
