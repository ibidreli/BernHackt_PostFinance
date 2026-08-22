---
tags: [feature]
status: umgesetzt
issue: 3
---

# Kategorien-Explorer (Zoomable Circle Packing)

Spec: [[Issue 3 – Kategorien-Explorer]] · Referenz-Visualisierung: [data-to-viz.com/graph/circularpacking](https://www.data-to-viz.com/graph/circularpacking.html)

> [!note] Soll-Änderungen (22.08.2026, [[Sollstatus]]) — **alle umgesetzt**
> Ist die **zweite Hauptseite** und ersetzt die Overview/Dashboard-Seite — sie liegt jetzt auf **`/kategorien`** (Prognose ist Start). API-Entscheid vollzogen: nur noch die **REST-Variante** (`/api/v1/graph`), die OData-Graph-Routen sind entfernt. Die Anomalie-Ringe (Alert-Integration) waren **Pflicht statt nice-to-have** und sind drin; das Detailpanel hat "In Prognose simulieren" und "Future Me fragen".

## Die Idee

Die Transaktionsliste wird durch eine hierarchische **Circle-Packing-Visualisierung** ersetzt: Kreisfläche = Franken-Betrag, vier Ebenen (`Ausgaben → Transport → SBB → einzelne Buchung`), zoombar per Klick bis zur einzelnen Buchung, die ein Detailpanel öffnet. Warum Fläche statt Anzahl zählt: die Kantine hat 121 Buchungen aber nur CHF 1'616, die Miete 12 Buchungen und CHF 21'840.

## Geplante Kernmechaniken (aus dem Issue)

- **Ausgaben / Einnahmen / Beides:** In "Beides" zeigen zwei grosse Kreise nebeneinander direkt Überschuss oder Defizit des Monats — eine der stärksten Aussagen der Visualisierung.
- **Absolut ⇄ Delta-Toggle:** Delta gegen den **Median der letzten 3 Monate** (nicht Vormonat — sonst verzerrt ein Ausreisser-September den Folgemonat). Farbe nach server-berechnetem `delta.direction` (`favourable`/`unfavourable`), nicht nach Vorzeichen — sonst leuchtet eine Lohnerhöhung rot. Kreisgrösse bleibt beim Umschalten stehen, nur die Farbe wechselt.
- **12-Monats-Slider** mit animierten Übergängen; alle Monate werden vorgeladen und im Client gecacht, damit beim Ziehen kein Netzwerk-Request nötig ist.
- **`d3.pack()`, kein Force-Layout** — Positionen müssen deterministisch sein, sonst springt die Grafik bei jedem Slider-Schritt.
- Händler-Normalisierung beim Import (Amazon-Varianten unter einem Knoten), Umbuchungen (`is_transfer`) aus beiden Teilbäumen ausgeschlossen (sonst ~CHF 41'850 doppelt gezählt), Rückerstattungen netto gegen Ausgaben gerechnet.

## API (umgesetzt)

**REST, wie im Issue:** `GET /api/v1/graph?month=YYYY-MM&mode=absolute|delta&flow=expense|income|both` liefert den kompletten Baum mit Inline-Transaktionsobjekten an den Blättern (kein Nachladen); `GET /api/v1/graph/months` die Slider-Monate.

Die zeitweise parallel existierende OData-Variante (`GraphNodes`/`GraphMonths`, `graph_odata.py`) wurde am 22.08. **entfernt** (Routen + CSDL-Einträge) — der Explorer nutzt die REST-Variante, der Entscheid war damit gefallen.

## Status

**Backend umgesetzt, auf `main` (PR #10, konsolidiert am 22.08.):** `app/services/graph_service.py`, `app/schemas/graph.py`, `app/api/routes/graph.py` sowie die im Issue geforderte Merchant-Alias-Normalisierung (`app/services/merchant_normalization.py`).

**Frontend umgesetzt, auf `main` (PR #13 + Ausbau am 22.08.):** `pages/explorer/` + `core/graph.ts` (`d3-hierarchy`), jetzt auf Route **`/kategorien`** — Monats-Slider mit Client-Cache (ein `flow=both&mode=delta`-Request pro Monat deckt alle Toggle-Kombinationen), Ausgaben/Einnahmen/Beides, Absolut⇄Delta, Zoom/Fokus, Detailpanel mit Transaktionstabelle, Summary-Balken ab 15 Kindern. Der Slider scrubbt inzwischen **kontinuierlich mit Morph-Übergang** zwischen den Monaten.

Neu seit dem 22.08. ([[Sollstatus]]-Ausbau):

- **Alert-Ringe** (via `core/alerts.ts`, client-seitiger Join — siehe [[Alerts]]): Severity-Ringe um betroffene Kreise (danger/warning/info), während des Scrubbens ausgeblendet; Filter-Chip **"Nur Auffälligkeiten"** mit Zähler, dimmt nicht betroffene Kreise ohne Re-Packing; "Warum sehe ich das?"-Sätze im Rail und im Detailpanel. Deep-Links von der Prognose landen per Query-Param (`?month=…&tx=…` bzw. `?month=…&category=Main~Sub`) auf der passenden Blase.
- **Verbindungs-Buttons** im Detail-Rail ("Weiterdenken"): **"In Prognose simulieren"** (Merchant mit aktivem Abo → `cancel_recurring`, sonst `adjust_category` −50 %) und **"Future Me fragen"** (vorbefüllte `what_if`-Frage, wird nicht automatisch abgeschickt) — Übergabe über den consume-once Signal-Store `core/handoff.ts`.
