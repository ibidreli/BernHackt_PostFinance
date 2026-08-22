---
tags: [feature]
status: in-arbeit
issue: 3
---

# Kategorien-Explorer (Zoomable Circle Packing)

Spec: [[Issue 3 – Kategorien-Explorer]] · Referenz-Visualisierung: [data-to-viz.com/graph/circularpacking](https://www.data-to-viz.com/graph/circularpacking.html)

## Die Idee

Die Transaktionsliste wird durch eine hierarchische **Circle-Packing-Visualisierung** ersetzt: Kreisfläche = Franken-Betrag, vier Ebenen (`Ausgaben → Transport → SBB → einzelne Buchung`), zoombar per Klick bis zur einzelnen Buchung, die ein Detailpanel öffnet. Warum Fläche statt Anzahl zählt: die Kantine hat 121 Buchungen aber nur CHF 1'616, die Miete 12 Buchungen und CHF 21'840.

## Geplante Kernmechaniken (aus dem Issue)

- **Ausgaben / Einnahmen / Beides:** In "Beides" zeigen zwei grosse Kreise nebeneinander direkt Überschuss oder Defizit des Monats — eine der stärksten Aussagen der Visualisierung.
- **Absolut ⇄ Delta-Toggle:** Delta gegen den **Median der letzten 3 Monate** (nicht Vormonat — sonst verzerrt ein Ausreisser-September den Folgemonat). Farbe nach server-berechnetem `delta.direction` (`favourable`/`unfavourable`), nicht nach Vorzeichen — sonst leuchtet eine Lohnerhöhung rot. Kreisgrösse bleibt beim Umschalten stehen, nur die Farbe wechselt.
- **12-Monats-Slider** mit animierten Übergängen; alle Monate werden vorgeladen und im Client gecacht, damit beim Ziehen kein Netzwerk-Request nötig ist.
- **`d3.pack()`, kein Force-Layout** — Positionen müssen deterministisch sein, sonst springt die Grafik bei jedem Slider-Schritt.
- Händler-Normalisierung beim Import (Amazon-Varianten unter einem Knoten), Umbuchungen (`is_transfer`) aus beiden Teilbäumen ausgeschlossen (sonst ~CHF 41'850 doppelt gezählt), Rückerstattungen netto gegen Ausgaben gerechnet.

## API (umgesetzt)

Es existieren **zwei parallele Varianten** über demselben `graph_service`:

- **REST, wie im Issue:** `GET /api/v1/graph?month=YYYY-MM&mode=absolute|delta&flow=expense|income|both` liefert den kompletten Baum mit Inline-Transaktionsobjekten an den Blättern (kein Nachladen); `GET /api/v1/graph/months` die Slider-Monate.
- **OData:** `GET /api/v1/GraphNodes` (flache, filterbare Knotenliste für Drilldown, mit `include_transactions`/`max_level` und vollen Query-Optionen) und `GET /api/v1/GraphMonths`.

Sobald das Frontend gebaut wird, sollte das Team sich für **eine** Variante entscheiden und die andere entfernen.

## Status

**Backend umgesetzt, auf `main` (PR #10):** `app/services/graph_service.py`, `app/schemas/graph.py`, `app/api/routes/graph.py`, `app/api/routes/graph_odata.py` sowie die im Issue geforderte Merchant-Alias-Normalisierung (`app/services/merchant_normalization.py`). **Frontend fehlt komplett** — keine Route, kein Consumer der Graph-Endpunkte; die Circle-Packing-Visualisierung ist noch zu bauen.
