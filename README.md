# BernHackt_PostFinance

Project for Bern Hackt 2026

Challenge: [Beyond the List](https://www.bernhackt.ch/challenges/2026-beyond-the-list)

## Project Structure

```text
rhylog/
├── apps/
│   ├── api/    # FastAPI, OData, no DB (in-memory CSV)
│   └── web/    # Angular
└── ...
```

## Development

### WEB

The web application is built with Angular and Tailwind CSS.

```bash
cd apps/web
npm install
npm start
```

### AI tooling (MCP)

`.mcp.json` registers the [Angular CLI MCP server](https://angular.dev/ai/mcp) so AI
assistants can inspect the workspace, read version-aligned best practices, and run targets.
It is resolved through `npx`, so it works on any machine with a compatible Node.js — no
paths to edit. Nothing to install; your MCP client starts it automatically.

### API

The API is built with FastAPI, has no database (the CSV export is loaded into memory
at startup), and exposes an OData v4 service (metadata, `$filter`/`$select`/`$orderby`
etc.) for the forecast feature.

```bash
docker compose up --build
```

Starts the API at `http://localhost:8000` (Swagger UI at `/docs`, health check at
`/health`). The CSV under `/data` is bind-mounted, so swapping the file doesn't require
a rebuild.

API reference: [`apps/api/API.md`](apps/api/API.md) (endpoints, `$filter` grammar,
error format). Implementation status, found bugs, and known limitations, kept up to
date per build step: [`apps/api/STATUS.md`](apps/api/STATUS.md).

For local development without Docker:

```bash
cd apps/api
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
CSV_PATH=../../data/data_personal.csv uvicorn app.main:app --reload
```

### Data

Mock data is provided in `/data` as `.csv` files
