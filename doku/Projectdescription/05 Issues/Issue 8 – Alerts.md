---
tags: [issue]
status: umgesetzt
issue: 8
---

# Issue #8 — Alerts (Auffälligkeiten-Radar)

> [!important] Soll-Änderung (22.08.2026, [[Sollstatus]]): keine eigene Seite mehr — **so geliefert**: Backend in PR #15, die Alerts sind in [[Kategorien-Explorer]] (Ringe/Filter) und Prognose (Liste/Marker) integriert; Route `/alerts` entfällt. Die Schwellen wurden gegenüber dieser Spec rekalibriert (siehe Umsetzungsstand).

GitHub-Issue: *noch nicht erstellt* · Labels: `feature`, `frontend`, `backend`, `priority:medium` · Epic: Beyond the List · Abhängigkeit: Klassifikation/`outlier` aus [[Issue 4 – Zukunftsprognose]] wiederverwenden, nicht neu bauen · Feature-Note: [[Alerts]]

## Kern der Spec

Eine eigene Seite «Auffälligkeiten» (Route `/alerts`), die wichtige Ereignisse aus den Transaktionen hervorhebt, damit der User nicht jede Buchung einzeln durchgehen muss. Drei Alert-Typen mit fester Severity-Zuordnung: **`duplicate_charge`** (danger — gleicher Händler, gleicher Betrag, gleicher Tag, ≥ 2 Buchungen, ≥ CHF 20), **`large_payment`** (warning — bestehende Outlier-Klassifikation, > 3× Kategorie-Median und ≥ CHF 100, Floor gilt auch für den Selten-Kategorie-Zweig), **`category_spike`** (info — Monatssumme ≥ 2× des 6-Monats-Medians und Delta ≥ CHF 150, nur variable Buchungen, mindestens 3 Monate Historie).

Gemeinsame Guards gegen Fehlalarme: nur Ausgaben, interne Umbuchungen (`Sonstige Geldtransfers`, `Überträge`) ausgeschlossen, alle Schwellen env-überschreibbar. Leitsatz wie beim [[Abo-Radar]]: **Fehlalarme kosten Vertrauen.**

API: OData-EntitySet `GET /api/v1/Alerts` (deterministisch, im `lifespan` berechnet, volle `$filter`/`$orderby`/`$top`/`$count`-Unterstützung). Schema sprach-neutral mit Enums; die deutschen «Warum sehe ich das?»-Sätze rendert das Frontend. Seite mit KPI-Kacheln (Counts pro Severity), Typ-/Schweregrad-Filter, Kartenliste und Empty-State. Details: [[Alerts]].

## Umsetzungsstand

**Geliefert** (Stand 22.08.2026) — als Integration, ohne eigene Seite:

- **Backend auf `main` (PR #15):** `app/schemas/alert.py`, `app/services/alert_service.py`, `app/api/routes/alerts.py` plus Erweiterungen in `main.py` und `odata/metadata.py`; wiederverwendet wie geplant `classify_transactions`, `monthly_category_stats`, `group_key`. Das Schema trägt über die Spec hinaus `transaction_id`/`transaction_ids` (Basis der Deep-Links). Tests: `tests/test_alert_service.py` + `tests/test_alerts_route.py` (Teil des neu aufgebauten Test-Scaffolds mit 59 Tests, [[Projektstatus]]).
- **Rekalibrierte Schwellen** (ausgeliefert in `app/core/config.py`, teils strenger als diese Spec): `ALERT_DUPLICATE_MIN_CHF=20` (wie Spec), `ALERT_LARGE_PAYMENT_MIN_CHF=200` (Spec: 100), `ALERT_SPIKE_MULTIPLIER=2.5` (Spec: 2.0), `ALERT_SPIKE_MIN_DELTA_CHF=250` (Spec: 150), `ALERT_SPIKE_MIN_MONTHS=4` (Spec: 3), neu dazu `ALERT_LOOKBACK_MONTHS=12`.
- **Frontend-Integration** (statt KPI-Kacheln/Kartenliste): Severity-Ringe, "Nur Auffälligkeiten"-Filter und "Warum sehe ich das?"-Sätze im [[Kategorien-Explorer]]; Auffälligkeiten-Liste mit Deep-Links, Fixkosten-Warn-Punkte und "Treiber ansehen"-Link in der Prognose. Details: [[Alerts]].

## Offene Fragen

Schwellenkalibrierung gegen die echten Daten — *erledigt, Ergebnis sind die rekalibrierten Werte oben*; sind die 32 byte-identischen CSV-Zeilengruppen echte Doppelbuchungen oder Exportfehler?; `is_transfer` sauber implementieren statt der Kategorie-Heuristik (weiterhin offen, [[Projektstatus]]).
