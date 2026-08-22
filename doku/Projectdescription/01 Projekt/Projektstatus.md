---
tags: [projekt, status]
---

# Projektstatus

Stand: 22.08.2026, nach dem Merge von PR #12 (Future-Me Chatbot) und der zweiten Doku-/Code-Konsolidierung. Das Zielbild dazu steht in [[Sollstatus]]. Detail-Logs: `apps/api/STATUS_FEATURE_NR_4_BACKEND.md` (T0–T11 + QA-Runde) und `apps/api/STATUS_FEATURE_NR_5_BACKEND.md` (T0–T13, jetzt auf `main`).

## Übersicht nach Feature

| Feature                           | Backend                                                                                     | Frontend                                                               | Wo                                         |
| --------------------------------- | ------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------- | ------------------------------------------ |
| [[Zukunftsprognose & Simulation]] | ✅ fertig, QA-getestet                                                                       | ✅ fertig (Forecast-Seite mit Chart, Horizonten, Simulations-Panel)     | alles auf `main`                           |
| [[Future-Me Chatbot]]             | ✅ fertig: LLM-Pipeline mit OpenAI (PR #12), `cached`-Modus als Offline-Fallback             | ✅ fertig — am 22.08. auf die neuen `/assistant/*`-Endpunkte umgestellt | alles auf `main`                           |
| [[Kategorien-Explorer]]           | ✅ fertig (PR #10): `graph_service`, Merchant-Normalisierung, OData- **und** REST-Routen     | ✅ erste Version (PR #13): Explorer auf `/` mit D3, Monats-Slider, Delta-Modus                                           | Backend auf `main`                         |
| [[Abo-Radar]]                     | ⚠️ **Quellcode verloren** — war nur uncommitted, nie eingecheckt; nur `.pyc`-Bytecode übrig | ❌ leeres Verzeichnis `pages/abo-radar/`, keine Route                   | **gestrichen** laut [[Sollstatus]] — kein Neubau |
| [[Alerts]]                        | ❌ nicht begonnen (Definition steht)                                                         | ❌                                                                      | [[Issue 8 – Alerts]] ist die Spec          |

Die frühere Dashboard-/Overview-Seite wurde mit PR #13 gelöscht — auf `/` liegt jetzt der Kategorien-Explorer. Laut [[Sollstatus]] tauschen Prognose und Explorer noch die Routen (Prognose wird Start).

## Konsolidierung #2 (22.08., nach Merge PR #12)

- **Chatbot-Entscheid:** Beim Merge kollidierten zwei unabhängige Implementierungen — die getestete **LLM-Variante** vom Branch `5-…` (behalten) und eine regelbasierte OData-Variante von `feature/prognosis` (verworfen, war dort selbst als Platzhalter markiert). Endpunkte jetzt REST: `POST /api/v1/assistant/ask`, `GET /api/v1/assistant/suggestions` (`apps/api/ASSISTANT_API.md`).
- **Frontend nachgezogen:** `core/assistant.ts`, `assistant-chart.ts` und Template auf den neuen Contract umgestellt (neue Pfade, `suggestions`-Feld, diskriminierte Chart-Union mit `baseline_series`/`scenario_series`, nullable `facts`/`assumptions_used`, Rückfragen-Antwort = nur die Option mit `conversation_id`). Dazu neu: Fehleranzeige im Chat für 502/504 (LLM-Timeout/-Fehler werden nicht mehr stumm verschluckt).
- **Merge-Leichen entfernt:** `$metadata`-CSDL deklarierte noch die gelöschten OData-Actions `Ask`/`Suggestions` (bereinigt); `API.md` enthielt noch den kompletten alten Assistenz-Abschnitt (ersetzt durch Verweis auf `ASSISTANT_API.md`).
- **Betrieb:** `docker compose up` braucht jetzt zwingend `apps/api/app/.env` (`env_file`) und einen Image-Rebuild (`--build`, wegen `openai`-Dependency). Ohne Key: `ASSISTANT_MODE=cached`. Beides verifiziert: alle Endpunkte antworten, Rückfrage-Flow (Bar/Leasing) läuft end-to-end im `cached`-Modus.
- **Tests:** `tests/test_assistant.py` (21 Tests) gehörte zur verworfenen Variante und wurde beim Merge **entfernt** — auf `main` gibt es aktuell **keine automatisierten Tests**, nur die `inspect_*`-Skripte.
- Aus Konsolidierung #1 (vor dem Merge): `/odata` → `/api/v1` überall verifiziert; Abo-Radar-Quellcode-Verlust festgestellt (nur `.pyc` übrig); Doku-Statusangaben, kaputte Links und `API.md`-Duplikate bereinigt.

## Offene Punkte & bekannte Findings

- **Keine Tests mehr auf `main`** (siehe oben) — höchster Wert: Golden-Tests für `forecast()`, den `$filter`-Parser und den `cached`-Chatbot-Pfad (läuft ohne Key, CI-tauglich).
- **Akzeptanzkriterium nicht erfüllbar mit Sample-Daten:** "Jahresansicht zeigt 13. Monatslohn / Steuertermine / Quartalsrechnungen" — der Datensatz enthält kein solches Muster ([[Datengrundlage]]).
- **Doppelte Graph-API:** Der Explorer (PR #13) nutzt die REST-Variante (`/graph`, `/graph/months`) — der Entscheid ist damit gefallen; die OData-Variante (`GraphNodes`/`GraphMonths`) ist toter Code und sollte samt CSDL-Einträgen entfernt werden.
- **Replay nach Rückfrage:** "Neu rechnen" nach einer beantworteten Rückfrage stellt die Rückfrage erneut (Server merkt sich die Antwort nicht über die aufgelöste Konversation hinaus) — akzeptiert, aber fürs Pitch wissen.
- **Frontend-Robustheit:** Right-Rail ist desktop-only (`lg:flex`) — auf Mobile fehlen die Forecast-Controls ersatzlos; Sign-out-Button ohne Handler.
- **Robustheits-Kleinigkeiten Backend:** `$select`/`$filter` auf nicht existierende Felder liefern `null`/leere Liste statt Fehler; `OData-Version`-Header gilt auch für `/health` und die REST-Routen; CORS `*`, kein Auth (für den Hackathon ok). LLM-Nichtdeterminismus bei Folgefragen (`STATUS_FEATURE_NR_5_BACKEND.md`).
- **Namensfrage:** `README.md` sagt "rhylog", der Vault "Rhylog", die Sidebar "PostFinance / Horizons" — fürs Pitch auf einen Namen einigen.
- **Ungenutzte Daten:** `data/jeanine_*.csv` referenziert nichts im Code.

## Nächste Schritte (nach [[Sollstatus]], 22.08.)

1. **Routing & Shell:** Prognose wird Startseite (`/`), Explorer zieht auf `/kategorien`, Sidebar-Reihenfolge Prognose → Kategorien → Future Me; leeres Abo-Radar-Verzeichnis löschen ([[Abo-Radar]] ist gestrichen; Dashboard ist seit PR #13 weg).
2. **Explorer fertigstellen:** OData-Graph-Routen samt CSDL entfernen; Detailpanel-Links "In Prognose simulieren" / "Future Me fragen".
3. **Szenarien ausbauen:** neuer Adjustment-Typ `adjust_category` (Backend + Szenario-Panel), Kategorie→Prognose-Verlinkung.
4. **Alerts integriert umsetzen** — Backend nach [[Issue 8 – Alerts]], im Frontend als Ringe/Filter im Explorer und Marker in der Prognose statt eigener Seite.
5. **Future-Me-Verbindungen:** Hebel→Kategorien-Links, Szenario-Übernahme, vorbefüllte Fragen.

Parallel, unabhängig vom Zielbild: **Tests wieder aufbauen** (`forecast()`-Golden-Tests, `$filter`-Parser, `cached`-Chatbot-Pfad — läuft ohne API-Key) und der **Mobile-Fallback für die Right-Rail**.

## Abgeschlossene Meilensteine (Git-Historie)

`#1` Verzeichnisstruktur → `#2` Struktur-PR → T0–T11 Prognose-Backend inkl. Pitch-Fixes (sqrt-Band, Recurring-Plausibilität) und QA → `#7` Merge Prognose/Simulation → PR #10 Kategorien-Explorer-Backend → Forecast-/Assistant-Frontend auf `main` → `/odata` → `/api/v1`-Migration (`24ba87e`, `0155594`) → Konsolidierung #1 → **PR #12 Future-Me Chatbot (LLM)** → Frontend-Umstellung auf `/assistant/*` + Konsolidierung #2 → **PR #13 Kategorien-Explorer-Frontend** (D3, ersetzt Dashboard) (22.08.2026).
