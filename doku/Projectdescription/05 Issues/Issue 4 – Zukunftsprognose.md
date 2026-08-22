---
tags: [issue]
status: umgesetzt
issue: 4
---

# Issue #4 — Zukunftsprognose & Szenario-Simulation

[GitHub #4](https://github.com/ibidreli/BernHackt_PostFinance/issues/4) · **closed** (gemergt via PR #7) · Labels: `feature`, `frontend`, `backend`, `priority:high` · Epic: Beyond the List – Prognose · Feature-Note: [[Zukunftsprognose & Simulation]]

## Kern der Spec

Verfügbarer Betrag für vier Horizonte, Prognose als **Band** statt Linie, **kumulierte** Saldokurve, **Engpass-Datum** aus der unteren Bandgrenze, Simulation mit den Eingriffstypen und Demo-Presets ("Netflix kündigen", "Miete +200", "Kantine halbieren"), 600-ms-Animation mit Geisterlinie. Fachliche Grundlagen: Lohnperioden, Drei Töpfe, keine Zinsen. Der Prognosekern muss als eigenständiger Service aufrufbar sein (für den Chatbot). Umfangreiche Edge-Case-Tabelle (kein Saldo → 409 + Eingabefeld, < 6 Monate Historie, Lohntag nicht erkennbar → benannter Fallback, `effective_from` bei Kündigungen …).

## Umsetzungsstand gegen die Akzeptanzkriterien

QA-Runde end-to-end dokumentiert in `apps/api/STATUS_FEATURE_NR_4_BACKEND.md`:

- ✅ Alle 4 Horizonte valide; Invariante `series[-1] == free_to_spend` hält; Band an Tag 0 exakt 0-breit; `tight_date` nachweislich aus der unteren Grenze; Ausreisser ausgeschlossen und benannt; alle 4 Eingriffstypen einzeln und kombiniert rappengenau nachgerechnet; 6 Fehlerpfade sauber.
- ⚠️ **"Jahresansicht zeigt 13. Monatslohn / Steuertermine / Quartalsrechnungen"** ist mit dem Sample-Datensatz **nicht erfüllbar** — echte Datenlücke, kein Code-Fehler ([[Datengrundlage]]).
- Abweichungen (dokumentiert): `recurring_id` als String statt DB-Integer, "Kantine halbieren" nicht abbildbar (Team-Entscheid), `diff`-Vorzeichen "positiv = besser", `float` statt `Decimal`, Inspect-Skripte statt Unit-Tests.

## Offene Fragen aus dem Issue

Puffer-Default (CHF 0 vs. ein Monat Fixkosten), Serien-Auflösung bei `365d` (Woche vs. Tag), Kalibrierung der Ausreisser-Schwelle an echten Daten.
