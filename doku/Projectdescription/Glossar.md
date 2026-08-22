---
tags: [referenz]
---

# Glossar

**Topf 1 / 2 / 3** — Die [[Drei-Töpfe-Klassifikation]] jeder Transaktion: **fix** (Teil eines erkannten Rhythmus, deterministisch planbar), **variabel** (regelmässig schwankend, statistisch prognostiziert), **Ausreisser** (einmalig, aus der Prognose ausgeschlossen aber benannt).

**Lohnperiode** — Zeitraum von Lohneingang zu Lohneingang. Die Prognose rechnet in Lohnperioden statt Kalendermonaten, weil Lohn (25.), Miete (1.) und Abos über den Monat verteilt liegen. Der Lohntag wird aus der Historie erkannt ([[Recurring-Detection]]), nicht hart codiert.

**Band / Korridor** — Die Prognose als Fläche zwischen `lower_chf` (P25) und `upper_chf` (P75) um die Erwartungslinie (Median), gespeist aus der historischen Streuung der Topf-2-Kategorien. Wächst linear bis 1 Monat, danach √-gedämpft ([[Forecast-Service]]). "Band statt Linie", weil eine Zahl mit zwei Nachkommastellen falsche Genauigkeit vortäuscht.

**Engpass-Datum (`tight_date`)** — Erster Tag, an dem die **untere** Bandgrenze den Puffer unterschreitet — bewusst pessimistisch. `null`, wenn der Puffer im Horizont hält.

**`recurring_id`** — Eindeutige ID einer wiederkehrenden Zahlung: `merchant::category_main::flow` (z. B. `NETFLIX.COM::Wohnen::expense`). Zusammengesetzt, weil Merchant-Strings mehrdeutig sind ("LASTSCHRIFT", "PAYPAL" bezeichnen mehrere Zahlungen) — der reine Merchant-Schlüssel führte zum wichtigsten gefundenen Bug ([[Recurring-Detection]]).

**`is_active`** — Eine wiederkehrende Zahlung gilt als beendet, wenn seit **2 Intervallen** keine Buchung mehr kam.

**`amount_history`** — Verlauf der Betragsänderungen einer wiederkehrenden Zahlung (Netflix 20.90 → 21.90). Grundlage des [[Abo-Radar]]-Status `increased`; in der API per Default ausgeklammert (Payload).

**Horizont** — Prognosezeitraum: `next_salary` (bis zum nächsten Lohn, Default), `30d`, `90d`, `365d`; der Chatbot erweitert auf `present`/`1y`/`5y`/`10y` durch Extrapolation ([[Assistant-Pipeline]]).

**`assumptions`** — Pflichtfeld jeder Prognose-Antwort: Methoden, ausgeschlossene Ausreisser, `interest_applied: false`, Freitext-`notes`. Die Antwort auf die Jury-Frage "Woher kommen diese Zahlen?".

**Eingriff / Adjustment** — Einer der vier Simulations-Typen `cancel_recurring`, `adjust_recurring`, `add_recurring`, `one_off` ([[API-Referenz]]).

**EntitySet / Function / Action** — Die drei benutzten OData-Konzepte: abfragbare Sammlung (`RecurringPayments`), lesende Operation (`GetForecast`, `GetSubscriptions`), schreibende Operation (`Simulate`). Siehe [[OData-Layer]].

**Flow** — Richtung einer Buchung: `expense` oder `income`, abgeleitet aus Lastschrift-/Gutschrift-Spalte ([[Datengrundlage]]).

**Hebel (Lever)** — Im Chatbot: die variablen Kategorien mit dem höchsten Monatsdurchschnitt, als konkreter Sparvorschlag in `no_unless`-Antworten. `potential_chf` = Differenz zum eigenen historischen Monats-Minimum.

**`ASSISTANT_MODE`** — `live` (echte OpenAI-Calls) oder `cached` (Demo-Fallback ohne externe Calls; gerechnet wird trotzdem echt). [[Setup & Betrieb]].
