---
tags: [issue]
status: in-arbeit
issue: 6
---

# Issue #6 — Abo-Radar (eigene View)

[GitHub #6](https://github.com/ibidreli/BernHackt_PostFinance/issues/6) · **open** · Labels: `feature`, `frontend`, `backend`, `priority:medium` · Epic: Beyond the List – Fixkosten · Abhängigkeit: `recurring_payment` aus [[Issue 4 – Zukunftsprognose]], nicht neu bauen · Feature-Note: [[Abo-Radar]]

## Kern der Spec

Eine Zeile pro Abo mit horizontalem 12-Monats-Balken (Lücke = fehlende Zahlung, Farbwechsel = Preisänderung, frühes Ende = weggefallen). Statuskategorien `new`/`increased`/`decreased`/`ended`/`unchanged` plus Edge-Case `variable` für schwankende Rechnungen (BKW-Fall: nie als Preiserhöhung melden — Fehlalarme kosten Vertrauen). Kopfzeile mit drei Kennzahlen und dem Fixkostentag-Satz. Detailpanel mit Betragsverlauf, Buchungsliste und **"In Prognose simulieren"-Button**, der Feature 2 mit vorbelegtem `cancel_recurring` öffnet — er macht aus einer Beobachtung eine Handlung. Micro-Charges gruppiert und eingeklappt; `flow = income` (Lohn) ausgeblendet.

API laut Issue: `GET /api/v1/subscriptions`, ein Endpunkt für alles.

## Umsetzungsstand

Backend implementiert, aber **uncommitted auf `main`** ([[Projektstatus]]): [[Subscription-Service]] mit Statuslogik (dokumentierte Präzedenz, CV-Schwelle 10 %), 12-Monats-Grid, Kennzahlen und Fixkostentag. Abweichung: Endpunkt als OData-Function `GET /api/v1/GetSubscriptions` statt schlichtem REST `/api/v1/subscriptions` (konsistent mit dem [[OData-Layer]]); weitere dokumentierte Abweichungen im Schema. Frontend fehlt noch komplett.

## Offene Fragen aus dem Issue

Schwelle `variable` vs. `increased` (Vorschlag Variationskoeffizient > 10 % — so umgesetzt); Zeitfenster für `new` (3 Monate; bei nur 12 Monaten Historie wäre sonst alles aus Januar "neu").
