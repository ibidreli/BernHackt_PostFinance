---
tags: [projekt, status]
---

# Projektstatus

Stand: 22.08.2026. Detail-Logs: `apps/api/STATUS_FEATURE_NR_4_BACKEND.md` (T0–T11 + QA-Runde) und `apps/api/STATUS_FEATURE_NR_5_BACKEND.md` (auf Branch `origin/5-…`).

## Übersicht nach Feature

| Feature | Backend | Frontend | Wo |
|---|---|---|---|
| [[Zukunftsprognose & Simulation]] | ✅ fertig, QA-getestet | ✅ gebaut | Backend auf `main`; UI auf `origin/feature/prognosis` |
| [[Abo-Radar]] | 🔨 in Arbeit | ❌ | **uncommitted auf `main`** (subscriptions-Route/-Schema/-Service, metadata.py, main.py) |
| [[Future-Me Chatbot]] | ✅ gebaut | ✅ gebaut | `origin/feature/prognosis` (Pipeline, Tests) + `origin/5-feature-future-me-chatbot-…` (OpenAI-Setup, .env) |
| [[Kategorien-Explorer]] | ❌ nur leere Platzhalter (`graph.py`, `graph_service.py`, `schemas/graph.py`) | ❌ | Branch `origin/3-…` existiert, ist aber identisch mit `main` |

## Was auf `main` liegt

Kompletter Prognose-Backend-Stack ([[Datenmodell & Repositories]], [[Recurring-Detection]], [[Drei-Töpfe-Klassifikation]], [[Forecast-Service]], [[OData-Layer]], [[API-Referenz]]) plus Frontend-Shell ([[App-Shell & Navigation]]). Die QA-Runde hat alle Akzeptanzkriterien von [[Issue 4 – Zukunftsprognose]] end-to-end getestet — bis auf eines (siehe unten).

## Offene Punkte & bekannte Findings

- **Akzeptanzkriterium nicht erfüllbar mit Sample-Daten:** "Jahresansicht zeigt 13. Monatslohn / Steuertermine / Quartalsrechnungen" — der Datensatz enthält schlicht kein solches Muster ([[Datengrundlage]]). Optionen fürs Team: auf echte Daten hoffen oder eine synthetische Quartalsbuchung in die Demo-CSV einfügen.
- **Broken Links:** `README.md` und `API.md` verlinken `apps/api/STATUS.md`; die Datei wurde in `STATUS_FEATURE_NR_4_BACKEND.md` umbenannt.
- **Fehlende Dinge, die Issues fordern:** Unit-Tests für Forecast/Klassifikation (nur Inspect-Skripte vorhanden), Frontend-Tests generell (Vitest installiert, `skipTests: true`), `is_transfer`-Erkennung (bewusst nicht verdrahtet), "Kantine halbieren"-Szenario (bewusst nicht abbildbar, Team-Entscheid).
- **Robustheits-Kleinigkeiten:** `$select`/`$filter` auf nicht existierende Felder liefern `null`/leere Liste statt Fehler; `OData-Version`-Header gilt auch für `/health`.
- **Uncommitted:** die komplette [[Abo-Radar]]-Backend-Implementierung plus dieser Doku-Vault (`doku/`).

## Abgeschlossene Meilensteine (Git-Historie)

`#1` Verzeichnisstruktur → `#2` Struktur-PR → T0–T11 Prognose-Backend inkl. Pitch-Fixes (sqrt-Band, Recurring-Plausibilität) und QA → `#7` Merge des Prognose-/Simulations-Features.
