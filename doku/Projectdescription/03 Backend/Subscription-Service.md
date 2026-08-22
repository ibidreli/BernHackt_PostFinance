---
tags: [backend, algorithmus]
status: in-arbeit
---

# Subscription-Service

Code: `app/services/subscription_service.py` (~325 Zeilen, **uncommitted**) · Schemas: `app/schemas/subscription.py` · Route: `app/api/routes/subscriptions.py` (`GET /api/v1/GetSubscriptions`) · Feature: [[Abo-Radar]]

## Ansatz

Der Service leitet pro erkannter wiederkehrender Zahlung eine 12-Monats-Sicht ab — über **dieselbe Gruppierungs-Linse** (`group_key` + Same-Day-Collapse) wie die [[Recurring-Detection]], damit Radar und Prognose nie widersprüchliche Zahlen zeigen. Betrachtungsfenster: 12 Monate rückwärts ab der letzten Transaktion im Datensatz.

## Bausteine

- **`detect_status()`** → `ended | new | variable | increased | decreased | unchanged` mit dokumentierter **Präzedenz**: `ended` zuerst (keine Buchung seit 2 Intervallen), dann `new` (erste Buchung in den letzten 3 Monaten), dann `variable` **vor** `increased`/`decreased` — Variationskoeffizient der Beträge > 10 % heisst "schwankend", nicht "teurer geworden". Der BKW-Fall aus [[Issue 6 – Abo-Radar]]: eine Stromrechnung mit 192/220/210 als Preiserhöhung zu melden, wäre ein Fehlalarm, und Fehlalarme kosten Vertrauen.
- **`build_month_grid()`** → exakt 12 Zellen pro Abo mit `paid`/`missed` — die Datengrundlage für die Balken-Visualisierung; eine fehlende Zahlung ist eine Lücke, kein Statuswechsel.
- **`build_change()`** → `from_chf`/`to_chf`/`since`, Jahresmehrkosten (`yearly_impact_chf`) und kumulierte Mehrkosten seit der Erhöhung.
- **`yearly_delta()`** → Kopfzeilen-Kennzahl "Mehrkosten im Jahr".
- **`fixed_cost_day()`** → der Pitch-Satz "Bis zum n. jedes Monats arbeitest du für deine Fixkosten": Fixkostenanteil am Monatseinkommen, auf Kalendertage umgelegt.
- **Micro-Charges** (< CHF 5) werden als eigene, eingeklappte Gruppe geführt.

## Abweichungen vom Issue-Contract

Im Schema (`app/schemas/subscription.py`) dokumentiert. Die wichtigsten: ein einziger OData-Function-Endpunkt `GetSubscriptions` statt `GET /api/v1/subscriptions` (konsistent mit dem [[OData-Layer]]); die Detail-Panel-Buchungen werden gleich mitgeliefert (ein Request für die ganze Seite); `recurring_id` ist der zusammengesetzte String aus der [[Recurring-Detection]], kein Integer.

## Status

Backend implementiert, aber noch nicht committet ([[Projektstatus]]). Frontend (Balkenliste, Kopfzeile, Detailpanel, "In Prognose simulieren"-Button) steht aus.
