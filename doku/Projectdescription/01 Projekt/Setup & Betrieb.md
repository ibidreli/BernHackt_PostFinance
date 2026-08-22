---
tags: [projekt, howto]
---

# Setup & Betrieb

## API starten (Docker, empfohlen)

```bash
docker compose up --build
```

- API auf `http://localhost:8000`, **Swagger UI** unter `/docs`, **Health-Check** unter `/health` (ausführlicher Smoke-Test, siehe [[Architektur & Tech-Stack]]).
- `docker-compose.yml` bind-mountet `./data:/data:ro` (CSV tauschen ohne Rebuild, `CSV_PATH=/data/data_personal.csv`) und `./apps/api/app` für Live-Reload (`uvicorn --reload`).

## API lokal ohne Docker

```bash
cd apps/api
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
CSV_PATH=../../data/data_personal.csv uvicorn app.main:app --reload
```

## Web-App starten

```bash
cd apps/web
npm install
npm start        # http://localhost:4200
```

Node 24 (`.nvmrc`). Auf dem Branch `feature/prognosis` proxyt `proxy.conf.json` die Pfade `/api` und `/odata` auf `localhost:8000` — API muss dafür laufen.

## Chatbot-Konfiguration (Branch `origin/5-…`)

Der [[Future-Me Chatbot]] braucht `apps/api/app/.env` (Vorlage: `.env.example`, wird **nicht** committet):

| Variable | Bedeutung |
|---|---|
| `OPENAI_API_KEY` | Pflicht bei `ASSISTANT_MODE=live` — App **failt fast beim Start**, wenn er fehlt |
| `ASSISTANT_MODE` | `live` (echte OpenAI-Calls) oder `cached` (Demo-Fallback ohne externe Calls; [[Forecast-Service]] rechnet trotzdem echt) |
| `OPENAI_MODEL` | Default `gpt-4o-mini`, für beide LLM-Calls |
| `ASSISTANT_LLM_TIMEOUT_SECONDS` | Default 8; bei Timeout explizite Fehlermeldung, kein stiller Template-Fallback |

## Manuelle Verifikation statt Tests

```bash
docker compose run --rm api python -m app.inspect_forecast      # auch: inspect_balance, inspect_recurring, inspect_classification
```

> [!warning] Bekannte Stolpersteine
> - `README.md` und `API.md` verlinken auf `apps/api/STATUS.md` — die Datei heisst inzwischen `STATUS_FEATURE_NR_4_BACKEND.md` (Links broken, siehe [[Projektstatus]]).
> - Fehlt die CSV beim Start oder ist sie defekt, crasht der Container hart (Exception im Lifespan-Hook) ohne freundliche Meldung.
