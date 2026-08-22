---
tags: [backend, algorithmus]
---

# Forecast-Service

Code: `app/services/forecast_service.py` (~600 Zeilen) · Schemas: `app/schemas/forecast.py` · Feature: [[Zukunftsprognose & Simulation]]

Der Prognosekern des Projekts. `forecast()` und `simulate()` sind **reine Funktionen ohne HTTP-/`app.state`-Abhängigkeit** — deshalb kann die [[Assistant-Pipeline]] sie direkt aufrufen (Akzeptanzkriterium aus [[Issue 4 – Zukunftsprognose]]).

## `forecast(horizon, as_of)` — Schritt für Schritt

1. **Startsaldo** von `BalanceRepository.as_of()` ([[Datenmodell & Repositories]]); kein Saldo → `NoBalanceAvailableError` (HTTP 409).
2. **Horizontende:** bei `next_salary` der nächste erkannte Lohneingang (Lohnperioden statt Kalendermonate), sonst +30/90/365 Tage.
3. **Topf-1-Events** ([[Drei-Töpfe-Klassifikation]]): jede aktive wiederkehrende Zahlung wird von ihrem eigenen `last_seen` + Intervall vorwärtsprojiziert — jede Position auf ihrem eigenen Rhythmus, nichts auf Monatsanfänge geschnappt. Erscheinen als `known_payments` mit Datum und Betrag.
4. **Topf-2-Baseline:** pro Kategorie P25/Median/P75 der Monatssummen (`monthly_category_stats`, 6 volle Monate), über Kategorien summiert (Unabhängigkeits-Annahme, im Moduldocstring dokumentiert).
5. **Serie:** tägliche kumulierte Saldokurve `expected/lower/upper`. Invariante (QA-geprüft): `series[-1] == free_to_spend`; das Band ist an Tag 0 exakt 0 breit und wächst nur durch variable Ausgaben — Fixkosten verschieben alle drei Kurven gleich.
6. **`tight_date`:** erster Tag, an dem die **untere** Bandgrenze den Puffer (Default CHF 0) unterschreitet — bewusst die pessimistische Kurve. `days_before_salary` wird gegen den Lohn **nach** dem Engpass gerechnet (Bug-Fix: bei 90d/365d war der Wert sonst negativ). Kein Unterschreiten → `null`.
7. **`assumptions`** zusammenstellen ([[API-Referenz]]).

## Die Band-Formel (Pitch-Fix mit Geschichte)

Ursprünglich wuchs die Bandbreite linear (Tagesrate × Tage) → bei 365d eine unglaubwürdige Spanne von ~CHF 15'852. Fix: der **Erwartungswert** wächst weiter linear, die **Bandbreite** um ihn herum linear nur bis 1 Monat und danach mit **√Monate** (Zentraler Grenzwertsatz: die Streuung einer Summe unabhängiger Monate wächst mit der Wurzel). Dabei selbst gefundene Regression: pure √-Skalierung hätte Horizonte **unter** einem Monat verbreitert (√x > x für x < 1) — genau die Standardansicht "bis zum Lohn". Final: linear bis 1 Monat, dann √-gedämpft, stetig am Übergang. 365d-Spanne: CHF 4'726 (Faktor ~3.35 ≈ √12).

## `simulate(horizon, adjustments)`

Wendet die vier Eingriffstypen aus der [[API-Referenz]] via `_apply_adjustments()` auf die Topf-1-Events an und rechnet Baseline **und** Szenario in einer Antwort. `_monthly_equivalent_impact()` liefert `diff.monthly_chf`; Konvention durchgehend `scenario − baseline`, **positiv = besser** (mehr Saldo, mehr Puffer-Tage, konsistent mit `tight_date_shift_days`).

Gefundene & gefixte Bugs: `one_off` mit positivem Betrag wurde als Einnahme verbucht (ein simulierter CHF-30'000-Autokauf **erhöhte** den Saldo) → jetzt immer positive Ausgaben-Magnitude; und der `recurring_id`-Eindeutigkeits-Bug ([[Recurring-Detection]]).

## Grenzen (dokumentiert)

- "Kantine halbieren" (Topf-2-Kategorie prozentual anpassen) ist mit den vier Typen nicht abbildbar — Team-Entscheid, kein 5. Typ.
- `diff.cumulative_series` alignt per Listenposition (`zip`), setzt identische Datumsachsen voraus — gilt für alle Demo-Presets, aber nicht falls ein Eingriff den Lohn selbst verschöbe.
- Perzentil-Summierung nimmt Unabhängigkeit zwischen Kategorien an (keine Kovarianz).
