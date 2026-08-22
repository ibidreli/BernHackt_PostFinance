---
tags: [frontend, ai]
status: in-arbeit
branch: origin/feature/prognosis
---

# Assistant-Seite

Code (Branch `origin/feature/prognosis`): `apps/web/src/app/pages/assistant/assistant.ts|.html`, `assistant-chart.ts`, Typen/Client in `app/core/assistant.ts` · Feature: [[Future-Me Chatbot]] · Backend: [[Assistant-Pipeline]]

## Aufbau

- **Chat-Oberfläche** mit Horizont-Umschalter (Heute / 1 / 5 / 10 Jahre) und Vorschlags-Chips (aus `GET /assistant/suggestions`) — sie senken die Hürde und lenken auf die drei unterstützten Fragetypen.
- **Annahmen-Regler** (Lohnwachstum, Inflation, Sparquote) neben dem Chat; die verwendeten Werte stehen unter jeder Antwort im Klartext (`assumptions_used`).
- **Rückfragen als Button-Gruppe** im Chatverlauf (nie offene Textfragen — Beamer-Regel).
- **Chart-Rendering** (`assistant-chart.ts`) für die drei festen Typen `wealth_over_time`, `goal_progress`, `before_after` — das Frontend rendert nur, was der Server als `chart`-Objekt liefert; Typen als diskriminierte Union in `core/assistant.ts` (`Facts`, `Lever`, `ChartSpec`).
- **Hebel-Darstellung** unter `no_unless`-Antworten: Kategorie, Monatsdurchschnitt, Einsparpotenzial.

## Verwandt

[[App-Shell & Navigation]] · [[Forecast-Seite]]
