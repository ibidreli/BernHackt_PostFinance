---
tags: [projekt, status]
---

# Projektstatus

Stand: 22.08.2026, nach der grossen Umsetzungsrunde des [[Sollstatus]] (Phasen 1–5: Routing-Tausch, OData-Graph-Entfernung, `adjust_category`, Alert-Integration, Future-Me-Verbindungen) plus Test-Neuaufbau und Mobile-Fallback. Detail-Logs: `apps/api/STATUS_FEATURE_NR_4_BACKEND.md` (T0–T11 + QA-Runde) und `apps/api/STATUS_FEATURE_NR_5_BACKEND.md` (T0–T13, auf `main`).

## Übersicht nach Feature

| Feature                           | Backend                                                                                     | Frontend                                                               | Wo                                         |
| --------------------------------- | ------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------- | ------------------------------------------ |
| [[Zukunftsprognose & Simulation]] | ✅ fertig, QA-getestet; neu inkl. `adjust_category` als fünftem Eingriffstyp                 | ✅ fertig — jetzt Startseite (`/`), mit "Kategorie anpassen"-Form, Auffälligkeiten-Liste und verlinkter Fixkosten-Liste | alles auf `main`                           |
| [[Future-Me Chatbot]]             | ✅ fertig: LLM-Pipeline mit OpenAI (PR #12), `cached`-Modus als Offline-Fallback; `what_if` versteht jetzt Kategorie-Prozent-Fragen | ✅ fertig — auf `/future-me`, mit Szenario-Übernahme, Hebel-Links und Prefill aus den anderen Seiten | alles auf `main`                           |
| [[Kategorien-Explorer]]           | ✅ fertig: `graph_service`, Merchant-Normalisierung, nur noch REST-Routen (OData-Variante entfernt) | ✅ fertig — auf `/kategorien`, mit Alert-Ringen, "Nur Auffälligkeiten"-Filter und Verbindungs-Buttons | alles auf `main`                           |
| [[Abo-Radar]]                     | ⚠️ **Quellcode verloren** — war nur uncommitted, nie eingecheckt; nur `.pyc`-Bytecode übrig | ✅ leeres Verzeichnis `pages/abo-radar/` gelöscht                       | **gestrichen** laut [[Sollstatus]] — kein Neubau |
| [[Alerts]]                        | ✅ fertig (PR #15): `alert_service`, `GET /api/v1/Alerts` als EntitySet                      | ✅ integriert statt eigener Seite: Ringe/Filter/„Warum sehe ich das?" im Explorer, Liste + Marker in der Prognose | alles auf `main`                           |

Die frühere Dashboard-/Overview-Seite wurde mit PR #13 gelöscht. Der Routen-Tausch aus dem [[Sollstatus]] ist vollzogen: **Prognose ist Startseite (`/`)**, der Explorer liegt auf `/kategorien`, der Assistent auf `/future-me` (Label "Future Me"); Redirects `forecast` → `/`, `assistant` → `/future-me`, Wildcard → `/`.

## Konsolidierung #2 (22.08., nach Merge PR #12)

- **Chatbot-Entscheid:** Beim Merge kollidierten zwei unabhängige Implementierungen — die getestete **LLM-Variante** vom Branch `5-…` (behalten) und eine regelbasierte OData-Variante von `feature/prognosis` (verworfen, war dort selbst als Platzhalter markiert). Endpunkte jetzt REST: `POST /api/v1/assistant/ask`, `GET /api/v1/assistant/suggestions` (`apps/api/ASSISTANT_API.md`).
- **Frontend nachgezogen:** `core/assistant.ts`, `assistant-chart.ts` und Template auf den neuen Contract umgestellt (neue Pfade, `suggestions`-Feld, diskriminierte Chart-Union mit `baseline_series`/`scenario_series`, nullable `facts`/`assumptions_used`, Rückfragen-Antwort = nur die Option mit `conversation_id`). Dazu neu: Fehleranzeige im Chat für 502/504 (LLM-Timeout/-Fehler werden nicht mehr stumm verschluckt).
- **Merge-Leichen entfernt:** `$metadata`-CSDL deklarierte noch die gelöschten OData-Actions `Ask`/`Suggestions` (bereinigt); `API.md` enthielt noch den kompletten alten Assistenz-Abschnitt (ersetzt durch Verweis auf `ASSISTANT_API.md`).
- **Betrieb:** `docker compose up` braucht jetzt zwingend `apps/api/app/.env` (`env_file`) und einen Image-Rebuild (`--build`, wegen `openai`-Dependency). Ohne Key: `ASSISTANT_MODE=cached`. Beides verifiziert: alle Endpunkte antworten, Rückfrage-Flow (Bar/Leasing) läuft end-to-end im `cached`-Modus.
- **Tests:** `tests/test_assistant.py` (21 Tests) gehörte zur verworfenen Variante und wurde beim Merge **entfernt** — damit gab es zwischenzeitlich keine automatisierten Tests auf `main`, nur die `inspect_*`-Skripte. *(Inzwischen behoben — siehe "Erledigte Findings" unten.)*
- Aus Konsolidierung #1 (vor dem Merge): `/odata` → `/api/v1` überall verifiziert; Abo-Radar-Quellcode-Verlust festgestellt (nur `.pyc` übrig); Doku-Statusangaben, kaputte Links und `API.md`-Duplikate bereinigt.

## Erledigte Findings (22.08., Umsetzungsrunde)

- **Tests wieder aufgebaut:** `apps/api/tests/` enthält jetzt `conftest.py` + `test_forecast_service.py` (Golden-Tests mit fixiertem `as_of=2026-06-15`), `test_odata_query.py` (`$filter`-Parser), `test_alerts_route.py` (HTTP), `test_assistant_cached.py` (keyless `cached`-Pfad), `test_adjust_category.py` und das bestehende `test_alert_service.py` — **59 Tests, alle grün**, laufen ohne `OPENAI_API_KEY` (`conftest` erzwingt `ASSISTANT_MODE=cached`). Ausführung: `docker compose exec api python -m pytest tests` (das `tests`-Verzeichnis ist jetzt in `docker-compose.yml` gemountet) oder lokal mit Python 3.12.
- **Doppelte Graph-API aufgelöst:** `graph_odata.py` samt `GraphNodes`/`GraphMonths`-Routen, CSDL-Einträgen und `flatten_graph_nodes()` entfernt — es gibt nur noch die REST-Variante `GET /api/v1/graph` + `/graph/months`, konsumiert vom Explorer.
- **Frontend-Robustheit behoben:** unterhalb `lg` öffnet ein schwebender "Optionen"-Button die Right-Rail als Bottom-Sheet (Dialog-Semantik, Escape/Backdrop, schliesst bei Navigation); der tote Sign-out-Button ist entfernt (es gibt kein Auth).
- **Backend-Robustheit:** unbekannte Felder in `$filter`/`$select`/`$orderby` liefern jetzt **400** mit OData-Error statt stiller `null`-Spalten/leerer Listen; der `OData-Version`-Header liegt nur noch auf den OData-Routen, nicht mehr auf `/health`, `/graph*` und `/assistant/*`.
- **Namensfrage entschieden:** Der Produktname ist **"PostFinance Horizons"** — README, Vault und Sidebar sind vereinheitlicht.
- **Akzeptanzkriterien-Lücke explizit akzeptiert:** "Jahresansicht zeigt 13. Monatslohn / Steuertermine / Quartalsrechnungen" kann mit der eingecheckten Sample-CSV nicht feuern — der Datensatz enthält kein solches Muster ([[Datengrundlage]]). Team-Entscheid: die CSV bleibt unangetastet (keine synthetischen Daten), die Lücke wird in Kauf genommen.

## Offene Punkte & bekannte Findings

- **Replay nach Rückfrage:** "Neu rechnen" nach einer beantworteten Rückfrage stellt die Rückfrage erneut (Server merkt sich die Antwort nicht über die aufgelöste Konversation hinaus) — akzeptiert, aber fürs Pitch wissen.
- **LLM-Nichtdeterminismus** bei Folgefragen (`STATUS_FEATURE_NR_5_BACKEND.md`).
- **CORS `*`, kein Auth** — für den Hackathon ok.
- **`is_transfer`** bleibt eine Kategorie-Heuristik (`Sonstige Geldtransfers`, `Überträge`), keine saubere Implementierung.
- **Ungenutzte Daten:** `data/jeanine_*.csv` referenziert nichts im Code.

## Nächste Schritte

Die fünf Umsetzungsphasen des [[Sollstatus]] (Routing & Shell, Explorer-Konsolidierung, `adjust_category`, Alert-Integration, Future-Me-Verbindungen) sind **umgesetzt**, ebenso die parallelen Aufgaben Tests und Mobile-Fallback. Was bleibt, ist Pitch-Vorbereitung und Feinschliff — plus die bewusst offen gelassenen Findings oben.

## Abgeschlossene Meilensteine (Git-Historie)

`#1` Verzeichnisstruktur → `#2` Struktur-PR → T0–T11 Prognose-Backend inkl. Pitch-Fixes (sqrt-Band, Recurring-Plausibilität) und QA → `#7` Merge Prognose/Simulation → PR #10 Kategorien-Explorer-Backend → Forecast-/Assistant-Frontend auf `main` → `/odata` → `/api/v1`-Migration (`24ba87e`, `0155594`) → Konsolidierung #1 → **PR #12 Future-Me Chatbot (LLM)** → Frontend-Umstellung auf `/assistant/*` + Konsolidierung #2 → **PR #13 Kategorien-Explorer-Frontend** (D3, ersetzt Dashboard) → **PR #15 Alerts-Backend** → **Sollstatus-Umsetzung Phasen 1–5** (Routing-Tausch, OData-Graph-Entfernung, `adjust_category`, Alert-Integration im Frontend, Future-Me-Verbindungen) + Test-Neuaufbau (59 Tests) + Mobile-Rail-Fallback (22.08.2026).
