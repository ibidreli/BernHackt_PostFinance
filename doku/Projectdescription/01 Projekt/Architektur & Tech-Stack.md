---
tags: [projekt, architektur]
---

# Architektur & Tech-Stack

## Monorepo

```
BernHackt_PostFinance/
├── apps/
│   ├── api/        # Python FastAPI + OData v4, keine DB (CSV in-memory)
│   └── web/        # Angular 22 + Tailwind 4 + daisyUI
├── data/           # Mock-CSV-Bankexporte
├── design/         # Farbpalette, Logos
├── doku/           # dieser Obsidian-Vault
├── docker-compose.yml
└── .mcp.json       # Angular-CLI-MCP-Server für AI-Tooling
```

## Backend (apps/api)

- **Python 3.12**, FastAPI 0.115, pandas 2.2, Pydantic 2.10, uvicorn — mehr nicht (auf `main`).
- **Keine Datenbank.** Der CSV-Export ist die einzige Datenquelle und wird beim Start einmal in den Speicher geladen (`lifespan`-Hook in `apps/api/app/main.py`). Kein Persistenz-Layer, keine Migration — bewusste Abweichung vom Issue-Datenmodell.
- **OData v4, pragmatisches Subset** statt REST: `@odata.context`-Envelope, `$filter/$select/$orderby/$top/$skip/$count`, statisches `$metadata`-CSDL, OData-Fehlerformat. Details: [[OData-Layer]].
- Schichten: `repositories/` (Daten) → `services/` (Fachlogik, reine Funktionen ohne HTTP) → `schemas/` (Pydantic-Contracts) → `api/routes/` (dünne OData-Endpunkte). Siehe [[Datenmodell & Repositories]].
- Statt Test-Suite: manuelle **Inspect-Skripte** (`app/inspect_forecast.py` u. a., via `docker compose run --rm api python -m app.inspect_forecast`). Einzige echte Testdatei: `tests/test_assistant.py` auf dem Prognose-Branch.

## Datenfluss beim Start

```
CSV (data/data_personal.csv)
  → data/data_personal.py            (rohes DataFrame)
  → TransactionRepository            (Merchant-Regex, Kategorien, Vorzeichen)  → app.state
  → BalanceRepository                (Saldo-Rekonstruktion)                    → app.state
  → recurring_detection              (197 wiederkehrende Zahlungen)            → app.state
  → classification                   (Drei Töpfe: fix/variabel/Ausreisser)     → app.state
```

Pro Request rechnen [[Forecast-Service]] / [[Subscription-Service]] auf diesen vorbereiteten Strukturen. `GET /health` ist zugleich Smoke-Test: Zeilenzahlen, erkannter Lohntag, Topf-Verteilung, eine komplette `next_salary`-Prognose.

## Frontend (apps/web)

- **Angular 22** (Standalone Components, Signals, `input()`/`output()`, native Control Flow `@if/@for`, `@Service`-Decorator), **Tailwind CSS 4** + **daisyUI 5**, `@lucide/angular` für Icons, TypeScript ~6.0. Konventionen: [[App-Shell & Navigation]].
- Auf `main` existiert nur die Shell (Layout, Sidebar, Theme, Dashboard-Platzhalter); die Feature-Seiten [[Forecast-Seite]] und [[Assistant-Seite]] liegen auf `origin/feature/prognosis`, wo auch `proxy.conf.json` `/api` und `/odata` auf `localhost:8000` proxyt (Backend-Pfad `/odata` ist auf `origin/5-feature-future-me-chatbot-szenario-assistent` inzwischen zu `/api/v1` umbenannt, siehe [[OData-Layer]] — beim Merge nachzuziehen).

## AI-Tooling

`.mcp.json` registriert den [Angular-CLI-MCP-Server](https://angular.dev/ai/mcp) (via `npx`), damit AI-Assistenten den Workspace inspizieren und versionsgenaue Best Practices lesen können. `apps/web/.claude/CLAUDE.md` hält die Angular-Coding-Standards fest.

## Verwandt

[[Setup & Betrieb]] · [[Datengrundlage]] · [[API-Referenz]] · [[Projektstatus]]
