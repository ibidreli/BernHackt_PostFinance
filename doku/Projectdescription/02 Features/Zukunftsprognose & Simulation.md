---
tags: [feature]
status: umgesetzt
issue: 4
---

# Zukunftsprognose & Szenario-Simulation

Spec: [[Issue 4 – Zukunftsprognose]] · Backend: [[Forecast-Service]] · UI: [[Forecast-Seite]] · API: [[API-Referenz]]

## Die Idee

Die App beantwortet **"Wie viel kann ich noch ausgeben?"** — nicht mit einer Punktzahl mit zwei Nachkommastellen ("eine Lüge"), sondern mit:

1. **Einem Korridor:** `CHF 1'050 – 1'400, wahrscheinlich 1'250`. Das Band entsteht aus der echten historischen Streuung der variablen Kategorien (P25/Median/P75), siehe [[Drei-Töpfe-Klassifikation]].
2. **Einem Engpass-Datum:** "Reicht bis zum 19. — 4 Tage vor deinem Lohn." Ein Datum merkt man sich, einen Betrag nicht. Berechnet aus der **unteren** Bandgrenze (pessimistisch — eine Warnung, die zu spät kommt, ist wertlos).
3. **Live-Simulation:** Netflix kündigen, Miete +200, neues Abo, einmaliger Autokauf — Baseline und Szenario-Kurve in einer Antwort, Effekt **kumuliert** formuliert ("Nach 1 Jahr: CHF 251 mehr · Engpass 3 Tage später"), weil "CHF 20.90/Monat" keine Reaktion erzeugt.

## Fachliche Grundpfeiler

- **Lohnperioden statt Kalendermonate:** Der Lohntag wird aus der Historie erkannt (im Datensatz: Tag 25), nicht hart codiert. Wer in Kalendermonaten rechnet, zeigt am 25. Unsinn an.
- **Drei Töpfe:** fix (deterministisch eingeplant, kein Band) / regelmässig schwankend (Median + Band) / Ausreisser (raus aus der Prognose, aber in `assumptions.excluded_outliers` benannt — sonst sagt die App im Oktober eine zweite Las-Vegas-Reise voraus).
- **Vier Horizonte:** `next_salary` (Default), `30d`, `90d`, `365d`.
- **Keine Zinsen/Rendite:** reine Summierung, `assumptions.interest_applied` immer `false` — bewusste Abgrenzung.

## Status

Backend auf `main` fertig und in einer QA-Runde end-to-end gegen alle Akzeptanzkriterien getestet (Details und gefundene Bugs: [[Forecast-Service]], [[Projektstatus]]). Frontend ebenfalls auf `main` ([[Forecast-Seite]]). Der Prognosekern ist eine reine Funktion ohne HTTP-Abhängigkeit — Voraussetzung dafür, dass der [[Future-Me Chatbot]] ihn mitbenutzen kann.

## Bewusste Abweichungen vom Issue

- `recurring_id` ist ein zusammengesetzter String (`merchant::category::flow`), kein DB-Integer — es gibt keine DB, und Merchant-Namen allein sind nicht eindeutig ([[Glossar]]).
- ~~**"Kantine halbieren" ist nicht abbildbar** — keiner der vier Eingriffstypen erlaubt eine Topf-2-Kategorie-Anpassung; mit dem Team so bestätigt.~~ **Revidiert am 22.08. per [[Sollstatus]]:** es gibt jetzt einen fünften Eingriffstyp **`adjust_category`** — Felder `category_main`, optional `category_sub` (`null` = ganze Hauptkategorie), genau eines von `percent` (≥ −100) oder `delta_chf`, optional `effective_from` (knickt die Kurve mitten im Horizont). Skaliert Median/P25/P75 der getroffenen Kategorien in der variablen Baseline (das Band skaliert mit); `delta_chf` wird proportional auf die getroffenen Subkategorien verteilt; unbekannte Kategorie = stilles No-op (gleiche Philosophie wie bei vertippter `recurring_id`). Wirkt in `POST /Simulate`, in `project_long_term` (Assistent 1y/5y/10y), und `diff.monthly_chf` weist den freiwerdenden Betrag aus. Im Frontend als "Kategorie anpassen"-Form (Kategorie-Select + Prozent-Slider) im "+"-Popover der Prognose-Rail.
- `diff`-Vorzeichen: durchgehend **positiv = besser**, abweichend vom mehrdeutigen Issue-Beispiel.
