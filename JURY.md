# Jury

---
Larpers
Beyond the List
---

[Repo](https://github.com/ibidreli/BernHackt_PostFinance)

## Ausgangslage

### Worauf haben wir uns fokussiert?

- Klare Taskzuweisung: Trennung Frontend, Backend, Doku — parallele Arbeit ohne Blockaden
- Bewusster Scope: drei Features sauber statt fünf halb (Explorer-Graph, Zukunftsprognose/Simulation, Future-Me-Chat)

### Welche technischen Grundsatzentscheide haben wir gesetzt?

- **Dedizierte API statt Frontend-Logik**: FastAPI-Backend, das die Bank-CSV beim Start in den Speicher lädt — keine Datenbank, kein Persistenz-Layer, Datei tauschen genügt (bind-mounted im Docker-Setup)
- **OData v4 (pragmatisches Subset)** als API-Stil: `$metadata` (CSDL), `$filter`/`$select`/`$orderby`/`$top`/`$count`, OData-Envelope und -Fehlerformat — banknah, da PostFinance-Systeme auf Standards setzen
- **LLM rechnet nie**: Der Chat nutzt das Modell nur für Intent-Extraktion und Formulierung; alle Zahlen kommen deterministisch aus dem Forecast-Service

## Technischer Aufbau

### Welche Komponenten und Frameworks haben wir verwendet?

**Frontend**

- Angular (Signals, Standalone Components, `withFetch`-HttpClient): Routing, Rendering, Bundling
- TypeScript: Developer Experience, Bug Prevention
- Tailwind + DaisyUI: Prebuilt Components und Theming
- D3 (`d3-hierarchy`): Kategorien-Baum als interaktives Node-Netzwerk

**Backend**

- Python + FastAPI, Swagger UI unter `/docs`
- Handgeschriebener OData-Layer (Parser für `$filter`-Grammatik, CSDL-Metadata, Envelope) — kein Framework-Magic, jede Zeile erklärbar
- OpenAI (`gpt-4o-mini`) für die zwei LLM-Calls des Chats, per `ASSISTANT_MODE=cached` komplett offline demofähig
- Pytest-Suite (~650 Zeilen) über Forecast, Alerts, OData-Parser, Chat-Cache
- Docker Compose für reproduzierbares Setup

## Implementation

### Gibt es etwas Spezielles, was wir zur Implementation erwähnen wollen?

- **Recurring-Detection als transparente Heuristik**: Gruppierung nach normalisiertem Händler + Kategorie, Rhythmus (monthly/quarterly/yearly) aus Median der Abstände — bewusst kein Clustering/Fuzzy-Matching, Grenzen inline dokumentiert
- **Strikte Fehler statt stiller Defaults**: unbekannte Felder in `$filter` → 400 mit OData-Error; LLM-Timeout → 504 statt erfundener Antwort
- **Rückfrage-Flow deterministisch**: bei Mehrdeutigkeit liefert der Chat Options-Buttons; die Antwort wird ohne zweiten LLM-Call aufgelöst (Conversation-State serverseitig)
- **Doku als Deliverable**: `API.md`/`ASSISTANT_API.md` als Referenz plus STATUS-Dateien mit bekannten Bugs, Grenzen und *Warum*-Entscheidungen pro Build-Schritt

### Was ist aus technischer Sicht besonders cool an unserer Lösung?

- **Future-Me-Chat mit Diagramm**: zwei getrennte LLM-Calls (Extraktion sieht nur die Frage, Formulierung nur das fertige Ergebnis — nie Rohtransaktionen), Antwort-Status nuanciert (`yes`/`tight`/`no_unless` statt Ja/Nein), max. 3 konkrete Spar-Hebel, fester Chart-Typ pro Intent
- **Simulation in einer Antwort**: `POST /Simulate` liefert Baseline + Szenario gemeinsam (cancel/adjust/add/one_off) — das Frontend vergleicht ohne zweiten Request
- **D3-Explorer**: Kategorien-Graph aus den echten Daten, mit smoothem Morphing zwischen Monaten beim Slider-Ziehen
- **Alerts aus Transaktionsmustern**: Duplikate, ungewöhnlich grosse Zahlungen, Kategorie-Spikes — als OData-EntitySet abfragbar

## Abgrenzung / Offene Punkte

### Welche Abgrenzungen haben wir bewusst vorgenommen und damit nicht implementiert?

- **Abo-Radar**: existiert bereits am Markt, zu wenig Differenzierung — unsere Recurring-Detection liefert die Datenbasis trotzdem
- **Kein Zins/Rendite in der Prognose** (`interest_applied: false`): reine Summierung, ehrlich ausgewiesen statt Scheingenauigkeit
- **Cached-Modus = kontrollierter Demo-Fallback**, kein allgemeines Offline-NLU: exaktes Matching auf 5 Demo-Fragen, der Forecast rechnet dabei echt
