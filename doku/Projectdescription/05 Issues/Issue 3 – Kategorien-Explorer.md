---
tags: [issue]
status: offen
issue: 3
---

# Issue #3 — Kategorien-Explorer (Zoomable Circle Packing)

[GitHub #3](https://github.com/ibidreli/BernHackt_PostFinance/issues/3) · **open** · Labels: `feature`, `frontend`, `backend`, `priority:high` · Epic: Beyond the List – Kategorisierung · Feature-Note: [[Kategorien-Explorer]]

## Kern der Spec

4-Ebenen-Hierarchie (Flow → Gruppe → Merchant → Buchung) als zoombares Circle Packing mit `d3.pack()`, Kreisfläche ∝ CHF. Segmented Controls für Ausgaben/Einnahmen/Beides und Absolut/Delta (Delta gegen den **3-Monats-Median**, Farbe nach server-berechnetem `delta.direction`), 12-Monats-Slider mit Client-Cache (kein Request beim Ziehen), Detailpanel mit Originalbezeichnung (macht die Händler-Normalisierung nachprüfbar), Zusammenfassungsleiste ab 15 Kindern, Preset-Buttons für den Pitch. Nice to have: Anomalie-Ringe (`duplicate_charge` etc.).

Datenmodell-Anforderungen: selbstreferenzierender Kategoriebaum, `models/merchant.py` mit Alias-Normalisierung **beim Import** (damit Prognose und Chatbot mitprofitieren), `is_transfer`-Ausschluss (sonst ~CHF 41'850 doppelt), Rückerstattungs-Netting, FX-Umrechnung (Rohdaten haben `exchange_rate = 1.0` auch bei EUR).

API: `GET /api/v1/graph` (kompletter Baum mit Inline-Transaktionen an den Blättern) + `GET /api/v1/graph/months`.

## Umsetzungsstand

**Nicht begonnen** — nur leere Platzhalter (`app/api/routes/graph.py`, `app/services/graph_service.py`, `app/schemas/graph.py`); Branch `origin/3-…` identisch mit `main`. Siehe [[Projektstatus]].

## Offene Fragen aus dem Issue

"Beides" als Default oder Preset? FX fix oder pro Datum? Anomalien im `graph_service` oder eigener Service (empfohlen: eigener, damit Prognose/Chatbot ihn nutzen können)?
