# BernHackt_PostFinance

Project for Bern Hackt 2026

Challenge: [Beyond the List](https://www.bernhackt.ch/challenges/2026-beyond-the-list)

## Project Structure

```text
rhylog/
├── apps/
│   ├── api/    # TODO
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

### API

TODO

### Data

Mock data is provided in `/data` as `.csv` files
