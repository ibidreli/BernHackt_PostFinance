---
tags: [issue]
status: offen
issue: 8
---

# Issue #8 — Alerts (Auffälligkeiten-Radar)

> [!important] Soll-Änderung (22.08.2026, [[Sollstatus]]): keine eigene Seite mehr — Backend-Spec unverändert, die Alerts werden in [[Kategorien-Explorer]] (Ringe/Filter) und Prognose (Marker) integriert; Route `/alerts` entfällt.

GitHub-Issue: *noch nicht erstellt* · Labels: `feature`, `frontend`, `backend`, `priority:medium` · Epic: Beyond the List · Abhängigkeit: Klassifikation/`outlier` aus [[Issue 4 – Zukunftsprognose]] wiederverwenden, nicht neu bauen · Feature-Note: [[Alerts]]

## Kern der Spec

Eine eigene Seite «Auffälligkeiten» (Route `/alerts`), die wichtige Ereignisse aus den Transaktionen hervorhebt, damit der User nicht jede Buchung einzeln durchgehen muss. Drei Alert-Typen mit fester Severity-Zuordnung: **`duplicate_charge`** (danger — gleicher Händler, gleicher Betrag, gleicher Tag, ≥ 2 Buchungen, ≥ CHF 20), **`large_payment`** (warning — bestehende Outlier-Klassifikation, > 3× Kategorie-Median und ≥ CHF 100, Floor gilt auch für den Selten-Kategorie-Zweig), **`category_spike`** (info — Monatssumme ≥ 2× des 6-Monats-Medians und Delta ≥ CHF 150, nur variable Buchungen, mindestens 3 Monate Historie).

Gemeinsame Guards gegen Fehlalarme: nur Ausgaben, interne Umbuchungen (`Sonstige Geldtransfers`, `Überträge`) ausgeschlossen, alle Schwellen env-überschreibbar. Leitsatz wie beim [[Abo-Radar]]: **Fehlalarme kosten Vertrauen.**

API: OData-EntitySet `GET /api/v1/Alerts` (deterministisch, im `lifespan` berechnet, volle `$filter`/`$orderby`/`$top`/`$count`-Unterstützung). Schema sprach-neutral mit Enums; die deutschen «Warum sehe ich das?»-Sätze rendert das Frontend. Seite mit KPI-Kacheln (Counts pro Severity), Typ-/Schweregrad-Filter, Kartenliste und Empty-State. Details: [[Alerts]].

## Umsetzungsstand

Noch nicht begonnen. Geplant: Branch ab `main`; die Frontend-Infrastruktur (HttpClient-Provider, `proxy.conf.json` + `angular.json`-Eintrag, `--color-danger`/`--color-warning`-Tokens inkl. WCAG-Kommentaren) wird von `feature/prognosis` portiert, ebenso der Sidebar-Icon-Mechanismus. Backend-seitig werden `classify_transactions`, `monthly_category_stats` und `group_key` wiederverwendet; neu entstehen `app/schemas/alert.py`, `app/services/alert_service.py`, `app/api/routes/alerts.py` plus Erweiterungen in `main.py` und `odata/metadata.py`. Test-Scaffold (`requirements-dev.txt`, `tests/`) muss auf `main` neu aufgebaut werden — inklusive Negativ-Tests pro Alert-Typ.

## Offene Fragen

Schwellenkalibrierung gegen die echten Daten (`ALERT_SPIKE_MULTIPLIER` 2.0, Duplikat-Floor CHF 20, Spike-Delta CHF 150 — nach dem ersten Lauf 3–5 Alerts pro Typ von Hand gegen die CSV prüfen); sind die 32 byte-identischen CSV-Zeilengruppen echte Doppelbuchungen oder Exportfehler?; `is_transfer` sauber implementieren statt der Kategorie-Heuristik.
