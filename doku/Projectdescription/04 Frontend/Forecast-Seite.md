---
tags: [frontend]
status: umgesetzt
branch: main
---

# Forecast-Seite

Code (auf `main`): `apps/web/src/app/pages/forecast/forecast.ts|.html`, `forecast-chart.ts`, API-Client `app/core/forecast.ts` · Feature: [[Zukunftsprognose & Simulation]] · API: [[API-Referenz]]

## Aufbau

- **Kernaussage zuerst, nicht die Grafik** (Vorgabe aus [[Issue 4 – Zukunftsprognose]]): oben gross der freie Betrag und das Engpass-Datum ("Reicht bis zum 19. Dezember – 4 Tage vor deinem Lohn"), darunter kleiner der Korridor.
- **Custom-SVG-Chart** (`forecast-chart.ts`, ~240 Zeilen, keine Chart-Library): Erwartungslinie durchgezogen, Band als halbtransparente Fläche zwischen `lower_chf`/`upper_chf`, Fixkosten-Marker auf der Zeitachse, Engpass-Datum als vertikale Markierung, Puffer-/Nulllinie.
- **Horizont-Umschalter:** vier Buttons — "Bis Lohn" / 30 / 90 / 365 Tage.
- **Simulations-Panel:** Adjustment-**Presets werden aus den echten Daten abgeleitet** (aus `RecurringPayments`), nicht hartcodiert; aktive Eingriffe als Chips, einzeln entfernbar; Ergebniszeile kumuliert formuliert.
- **API-Client** `core/forecast.ts`: typisiert, auf Basis von Angulars `httpResource`; alle Requests gehen an `/api/v1`, `proxy.conf.json` leitet `/api` an `localhost:8000` weiter (Migration von `/odata` abgeschlossen, Commits `24ba87e`/`0155594` — siehe [[OData-Layer]]).

## Verwandt

[[App-Shell & Navigation]] · [[Assistant-Seite]] · [[Projektstatus]]
