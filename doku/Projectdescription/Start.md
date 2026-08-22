---
tags: [moc]
---

# PostFinance Horizons — Projektbeschreibung

Hackathon-Projekt für **BernHackt 2026**, Challenge [[Challenge & Ziel|"Beyond the List"]] von PostFinance: Transaktionslisten liefern Daten, aber keine Einsicht. Diese App macht aus einem Bank-CSV-Export **Prognosen, Visualisierungen und Antworten** — ohne Datenbank, ohne dass ein Sprachmodell je selbst rechnet.

> [!info] Orientierung
> Neu im Projekt? Lies [[Challenge & Ziel]] → [[Architektur & Tech-Stack]] → [[Setup & Betrieb]], dann das Feature, an dem du arbeitest. Der aktuelle Stand aller Baustellen steht in [[Projektstatus]].

## 01 Projekt

- [[Challenge & Ziel]] — die PostFinance-Challenge und was die App daraus macht
- [[Architektur & Tech-Stack]] — Monorepo, FastAPI + OData, Angular 22, Datenfluss
- [[Setup & Betrieb]] — wie man API und Web-App startet
- [[Datengrundlage]] — das Bank-CSV, seine Eigenheiten, die Mock-Daten
- [[Design-System]] — PostFinance-Farbpalette und Prinzipien
- [[Projektstatus]] — was fertig ist, was offen, was auf welchem Branch liegt
- [[Sollstatus]] — das Zielbild: drei verbundene Seiten (Prognose → Kategorien → Future Me) — umgesetzt

## 02 Features

| Feature | Issue | Status |
|---|---|---|
| [[Zukunftsprognose & Simulation]] | [[Issue 4 – Zukunftsprognose]] | ✅ Backend und Frontend auf `main`; Startseite (`/`), Szenarien inkl. `adjust_category` |
| [[Future-Me Chatbot]] | [[Issue 5 – Future-Me Chatbot]] | ✅ LLM-Backend auf `main` (PR #12) + UI auf `/future-me`; `cached`-Modus für Demos ohne Key; `what_if` versteht Kategorie-Fragen |
| [[Kategorien-Explorer]] | [[Issue 3 – Kategorien-Explorer]] | ✅ Backend (PR #10) + Frontend (PR #13 + Ausbau) auf `/kategorien` — mit Alert-Ringen und Verbindungs-Buttons |
| [[Alerts]] | [[Issue 8 – Alerts]] | ✅ Backend (PR #15) + integriert in Prognose und Kategorien — **keine eigene Seite** ([[Sollstatus]]) |
| [[Abo-Radar]] | [[Issue 6 – Abo-Radar]] | ❌ **gestrichen** ([[Sollstatus]]); Quellcode war verloren, Fixkosten-Sicht lebt in der Prognose weiter |

## 03 Backend

- [[API-Referenz]] — alle Endpunkte, `$filter`-Grammatik, Fehlerformat
- [[Datenmodell & Repositories]] — CSV → Transaktionen, Merchant-Extraktion, Saldo-Rekonstruktion
- [[Recurring-Detection]] — wie wiederkehrende Zahlungen erkannt werden
- [[Drei-Töpfe-Klassifikation]] — fix / variabel / Ausreisser
- [[Forecast-Service]] — der Prognosekern: Band, Engpass-Datum, Simulation
- [[Subscription-Service]] — die Abo-Radar-Logik (Spezifikation; Quellcode verloren)
- [[Assistant-Pipeline]] — die 6-Schritte-Chatbot-Architektur (LLM, auf `main`)
- [[OData-Layer]] — Envelope, `$filter`-Parser, CSDL-Metadata

## 04 Frontend

- [[App-Shell & Navigation]] — Layout, Sidebar, Theme, Angular-Konventionen
- [[Forecast-Seite]] — Prognose-UI mit SVG-Chart (auf `main`)
- [[Assistant-Seite]] — Chat-UI mit Annahmen-Reglern (auf `main`)

## Nachschlagen

- [[Glossar]] — Topf 1/2/3, `recurring_id`, Engpass-Datum, Lohnperiode …
