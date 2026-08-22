---
tags: [projekt, zielbild]
status: definiert
---

# Sollstatus (Zielbild)

Definiert am 22.08.2026. Ist-Stand dazu: [[Projektstatus]]. Dieses Dokument beschreibt, **wohin** die App sich entwickelt — drei verbundene Seiten statt vier isolierter Features.

## Leitidee

**Ein durchgehender Workflow statt einzelner Views:** Die Prognose zeigt, *wohin* das Geld läuft → der Kategorien-Explorer zeigt, *woher* die Zahlen kommen → Future Me beantwortet, *was wäre wenn*. Jede Seite verlinkt kontextuell in die anderen beiden; Auffälligkeiten (Alerts) erscheinen dort, wo die betroffenen Daten ohnehin sichtbar sind, nicht auf einer eigenen Seite.

## Navigation & Routen (Soll)

| Reihenfolge | Route | Seite | Heute (nach PR #13) |
|---|---|---|---|
| 1 (Start) | `/` | **Prognose** ([[Forecast-Seite]]) | heute unter `/forecast`; auf `/` liegt aktuell der Explorer |
| 2 | `/kategorien` | **Kategorien** ([[Kategorien-Explorer]]) | erste Version existiert (PR #13), liegt aber auf `/` |
| 3 | `/future-me` | **Future Me** ([[Assistant-Seite]]) | heute unter `/assistant` |

- Die **Overview/Dashboard-Seite ist bereits weg** — PR #13 hat `pages/dashboard/` gelöscht und durch die Explorer-Seite ersetzt. Was zum Soll noch fehlt, ist der **Routen-Tausch**: Prognose auf `/` (Start), Explorer auf `/kategorien`.
- **[[Abo-Radar]] ist aus dem Plan gestrichen** (Quellcode war ohnehin verloren). Was davon bleibt: die Abo-Sicht existiert als Teilmenge in der Prognose (Fixkosten-Liste aus `RecurringPayments`, Kündigungs-Szenarien) — keine eigene Seite, kein Neubau. `pages/abo-radar/` (leer) wird gelöscht, [[Issue 6 – Abo-Radar]] geschlossen.
- **[[Alerts]] wird keine eigene Seite** — Route `/alerts` entfällt; die drei Alert-Typen aus [[Issue 8 – Alerts]] werden in die bestehenden Seiten integriert (siehe unten). Backend-Spec (Typen, Schwellen, Guards, Schema) bleibt unverändert gültig.

## Seiten im Soll — und ihre Verbindungen

### 1. Prognose (Start)

Bleibt inhaltlich die heutige [[Forecast-Seite]], plus:

- **Ausgebaute Szenarien, kompatibel mit Kategorien:** neuer Adjustment-Typ **`adjust_category`** (Topf-2-Kategorie um Prozent oder CHF-Betrag senken/erhöhen, z. B. "Gastronomie −50 %"). Damit wird das bisher bewusst ausgeschlossene "Kantine halbieren"-Szenario abbildbar — **dieser Team-Entscheid aus Feature 4 wird hiermit revidiert**, weil die Kategorien-Seite genau solche Eingriffe nahelegt.
- **Links in die Kategorien-Seite:** jede `known_payment`-Zeile und jedes Szenario-Preset verlinkt auf den passenden Knoten im Explorer (`/kategorien?month=…&category=…`).
- **Alert-Integration:** `large_payment`-Alerts erscheinen als Warn-Marker an den betroffenen `known_payments`/Ausreisser-Hinweisen; ein `tight_date` mit gleichzeitigem `category_spike` bekommt einen Hinweis "Treiber ansehen" → Kategorien-Seite.
- **Link zu Future Me:** aktives Szenario → Button "Future Me dazu fragen" (öffnet `/future-me` mit vorbefüllter `what_if`-Frage).

### 2. Kategorien (ersetzt Overview)

Erste Version existiert seit PR #13 (`pages/explorer/`, `core/graph.ts` mit `d3-hierarchy`): Monats-Slider mit Client-Cache (ein Request pro Monat deckt alle Flow/Mode-Kombinationen), Ausgaben/Einnahmen/Beides, Absolut⇄Delta, Zoom/Fokus, Detailpanel mit Transaktionstabelle. Noch offen fürs Soll:

- **API-Entscheid ist damit faktisch gefallen:** die Seite nutzt die **REST-Variante** `GET /api/v1/graph` + `/graph/months`. Ausstehend: die OData-Variante `GraphNodes`/`GraphMonths` entfernen (Routen + CSDL-Einträge).
- **Alert-Integration** (die "Anomalie-Ringe" aus dem Issue, jetzt Pflicht statt nice-to-have): Knoten mit `duplicate_charge`- oder `large_payment`-Alert bekommen einen Severity-Ring/Badge; Kategorien mit `category_spike` einen Delta-Marker. Filter-Chip "Nur Auffälligkeiten". Der "Warum sehe ich das?"-Satz aus der Alerts-Spec erscheint im Detailpanel des Knotens.
- **Links in die Prognose:** Detailpanel jedes Kategorie-/Merchant-Knotens → "In Prognose simulieren" (öffnet `/` mit vorbefülltem `adjust_category`- bzw. `cancel_recurring`-Eingriff).
- **Link zu Future Me:** Detailpanel → "Future Me fragen" (vorbefüllte `what_if`-Frage zur Kategorie).

### 3. Future Me

Bleibt inhaltlich die heutige [[Assistant-Seite]], plus:

- **Hebel verlinken auf Kategorien:** jeder `lever` in einer Antwort → Drilldown des Kategorie-Knotens.
- **Szenario-Übernahme:** `what_if`-Antworten bekommen "Als Szenario in Prognose übernehmen" (übergibt den Eingriff an die Forecast-Seite).
- **Vorbefüllte Fragen** aus Prognose/Kategorien (Query-Param, landet im Eingabefeld, wird nicht automatisch abgeschickt).
- `what_if` versteht mit `adjust_category` auch Kategorie-Prozent-Fragen ("Was wäre, wenn ich Gastronomie halbiere?") — heute `unsupported`.

## Nötige Backend-Erweiterungen

1. **`adjust_category`** als fünfter Adjustment-Typ in `app/schemas/forecast.py` + `forecast_service.simulate()` (skaliert den Kategorie-Anteil der variablen Baseline; Felder: `category_main`, optional `category_sub`, `percent` **oder** `delta_chf`, optional `effective_from`). Auch von `assistant_service`/`intent_service` für `what_if` nutzbar.
2. **Alert-Service** nach [[Issue 8 – Alerts]] (`app/services/alert_service.py`, `schemas/alert.py`, `GET /api/v1/Alerts` als EntitySet) — unverändert zur Spec, nur ohne eigene Frontend-Seite. Kategorien- und Prognose-Seite konsumieren dieselbe Liste per `$filter`.
3. **Graph-API konsolidieren:** OData-Graph-Routen (`graph_odata.py`) und ihre CSDL-Typen entfernen, REST-Variante behält.
4. Optional fürs Verlinken: `graph`-Response um `alert_ids` pro Knoten ergänzen (oder das Frontend joint client-seitig über `category`/`merchant` — einfachster Start).

## Umsetzungsreihenfolge (Vorschlag)

1. **Routing & Shell:** Prognose auf `/` (Start), Explorer auf `/kategorien`, `/assistant` → `/future-me` (Redirects für alte Links), Sidebar-Reihenfolge Prognose → Kategorien → Future Me; leeres `pages/abo-radar/` löschen. *(Dashboard ist seit PR #13 schon weg.)*
2. **Explorer fertigstellen:** OData-Graph-Routen + CSDL-Einträge entfernen; "In Prognose simulieren"/"Future Me fragen" im Detailpanel.
3. **`adjust_category`** Backend + Szenario-Panel-Ausbau + Kategorie→Prognose-Link.
4. **Alert-Service** + Integration in Kategorien (Ringe/Filter) und Prognose (Marker).
5. **Future-Me-Verbindungen** (Hebel-Links, Szenario-Übernahme, vorbefüllte Fragen, `what_if` mit Kategorie).

Parallel dazu (aus [[Projektstatus]], unabhängig vom Zielbild): Tests wieder aufbauen — `forecast()`-Golden-Tests, `$filter`-Parser, `cached`-Chatbot-Pfad.

## Offene Entscheidungen

- **Szenario-Übergabe zwischen Seiten:** Query-Params (einfach, teilbar) vs. gemeinsamer Signal-Store (`core/`-Service) — Empfehlung: Service für den Live-Flow, Query-Params nur für Deep-Links auf die Kategorien-Seite.
- `adjust_category` in Prozent, CHF oder beides (Empfehlung: beides, Discriminator im Feld).
- Alert-Berechnung eager im `lifespan` (wie Spec) vs. lazy beim ersten Abruf — bei 5303 Zeilen ist eager unkritisch.

## Verwandt

[[Projektstatus]] · [[Challenge & Ziel]] · [[Kategorien-Explorer]] · [[Zukunftsprognose & Simulation]] · [[Future-Me Chatbot]] · [[Alerts]]
