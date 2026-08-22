---
tags: [projekt, status]
---

# Projektstatus

Stand: 22.08.2026, nach dem Merge von PR #12 (Future-Me Chatbot) und der zweiten Doku-/Code-Konsolidierung. Detail-Logs: `apps/api/STATUS_FEATURE_NR_4_BACKEND.md` (T0–T11 + QA-Runde) und `apps/api/STATUS_FEATURE_NR_5_BACKEND.md` (T0–T13, jetzt auf `main`).

## Übersicht nach Feature

| Feature | Backend | Frontend | Wo |
|---|---|---|---|
| [[Zukunftsprognose & Simulation]] | ✅ fertig, QA-getestet | ✅ fertig (Forecast-Seite mit Chart, Horizonten, Simulations-Panel) | alles auf `main` |
| [[Future-Me Chatbot]] | ✅ fertig: LLM-Pipeline mit OpenAI (PR #12), `cached`-Modus als Offline-Fallback | ✅ fertig — am 22.08. auf die neuen `/assistant/*`-Endpunkte umgestellt | alles auf `main` |
| [[Kategorien-Explorer]] | ✅ fertig (PR #10): `graph_service`, Merchant-Normalisierung, OData- **und** REST-Routen | ❌ kein Consumer, keine Route | Backend auf `main` |
| [[Abo-Radar]] | ⚠️ **Quellcode verloren** — war nur uncommitted, nie eingecheckt; nur `.pyc`-Bytecode übrig | ❌ leeres Verzeichnis `pages/abo-radar/`, keine Route | Neubau nach [[Subscription-Service]] nötig |
| [[Alerts]] | ❌ nicht begonnen (Definition steht) | ❌ | [[Issue 8 – Alerts]] ist die Spec |

Dashboard (Landing-Route): Platzhalter mit statischen Beispieldaten — noch kein echter Daten-Anschluss.

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
- **Doppelte Graph-API:** OData- (`GraphNodes`/`GraphMonths`) und REST-Variante (`/graph`, `/graph/months`) sind beide live, keine hat einen Frontend-Consumer. Beim Bau des Explorer-Frontends eine wählen, die andere entfernen.
- **Replay nach Rückfrage:** "Neu rechnen" nach einer beantworteten Rückfrage stellt die Rückfrage erneut (Server merkt sich die Antwort nicht über die aufgelöste Konversation hinaus) — akzeptiert, aber fürs Pitch wissen.
- **Frontend-Robustheit:** Right-Rail ist desktop-only (`lg:flex`) — auf Mobile fehlen die Forecast-Controls ersatzlos; Sign-out-Button ohne Handler.
- **Robustheits-Kleinigkeiten Backend:** `$select`/`$filter` auf nicht existierende Felder liefern `null`/leere Liste statt Fehler; `OData-Version`-Header gilt auch für `/health` und die REST-Routen; CORS `*`, kein Auth (für den Hackathon ok). LLM-Nichtdeterminismus bei Folgefragen (`STATUS_FEATURE_NR_5_BACKEND.md`).
- **Namensfrage:** `README.md` sagt "rhylog", der Vault "Rhylog", die Sidebar "PostFinance / Horizons" — fürs Pitch auf einen Namen einigen.
- **Ungenutzte Daten:** `data/jeanine_*.csv` referenziert nichts im Code.

## Nächste sinnvolle Schritte (Vorschläge, priorisiert)

1. **Kategorien-Explorer-Frontend** — das Backend liegt fertig brach; grösster Hebel fürs Demo.
2. **Tests wieder aufbauen** — der `cached`-Chatbot-Pfad plus `forecast()`-Golden-Tests laufen ohne API-Key.
3. **Dashboard an echte Daten anschliessen** — KPIs aus `GetForecast`/`RecurringPayments` (Free-to-spend, nächste Fixkosten, Engpass-Datum) statt der Fake-Kategorien.
4. **Abo-Radar neu bauen** (Spec: [[Subscription-Service]]) — oder vorher einen Dekompilierungs-Versuch der `.pyc`-Dateien.
5. **Alerts umsetzen** ([[Issue 8 – Alerts]]) — vollständig spezifiziert, `large_payment` kann die Outlier-Klassifikation direkt wiederverwenden.
6. **Mobile-Fallback für die Right-Rail** der Forecast-Seite.

## Abgeschlossene Meilensteine (Git-Historie)

`#1` Verzeichnisstruktur → `#2` Struktur-PR → T0–T11 Prognose-Backend inkl. Pitch-Fixes (sqrt-Band, Recurring-Plausibilität) und QA → `#7` Merge Prognose/Simulation → PR #10 Kategorien-Explorer-Backend → Forecast-/Assistant-Frontend auf `main` → `/odata` → `/api/v1`-Migration (`24ba87e`, `0155594`) → Konsolidierung #1 → **PR #12 Future-Me Chatbot (LLM)** → Frontend-Umstellung auf `/assistant/*` + Konsolidierung #2 (22.08.2026).
