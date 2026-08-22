---
tags: [frontend]
---

# App-Shell & Navigation

Code: `apps/web/src/app/` · Stack & Konventionen: [[Architektur & Tech-Stack]] · Farben: [[Design-System]]

## Aufbau auf `main`

- `main.ts` → `bootstrapApplication(App, appConfig)`; `app.ts` ist nur ein `<router-outlet />`.
- **`layout/dashboard-layout/`** — die Shell: einklappbare Sidebar, Header mit Toggle, Breadcrumb ("PostFinance › Home"), Hell/Dunkel-Umschalter, `<main>` mit Router-Outlet. Durchgehend ARIA-Attribute.
- **`layout/sidebar/`** — einklappbare Navigation (`w-64` ↔ `w-[72px]`), Branding "PostFinance / Horizons", Nav-Gruppen (aktuell nur "Tools → Overview"), Sign-out. Accessibility: `aria-current`, sr-only-Labels im eingeklappten Zustand.
- **`pages/dashboard/`** — Platzhalter mit drei hartcodierten Kategorie-Karten.
- **`core/theme.ts`** — `@Service()`-Store auf Signal-Basis: liest `localStorage`, fällt auf `prefers-color-scheme` zurück, toggelt per `effect` die `.dark`-Klasse auf `documentElement`.
- Routen (`app.routes.ts`, alle auf `main`): `''` → DashboardLayout mit lazy geladenem Dashboard (noch Platzhalter-Daten), `/forecast` ([[Forecast-Seite]]) und `/assistant` ([[Assistant-Seite]]), plus `core/rail.ts` (rechte Kontextspalte via `ng-template` + Directive) und `core/chart-theme.ts` (`chf()`-Formatter).

## Angular-Konventionen (aus `apps/web/.claude/CLAUDE.md`)

Verbindlich für alle Beiträge, auch von AI-Agenten:

- **Standalone Components** und **Signals**; `input()`/`output()` statt Decorators; `@Service`-Decorator (Angular 22+).
- Native Control Flow **`@if`/`@for`** statt `*ngIf`/`*ngFor`; **kein `ngClass`/`ngStyle`**.
- Signal Forms; Styling mit Tailwind 4 + daisyUI, semantische Theme-Tokens aus `styles.css`.
- **AXE/WCAG-AA**-Anforderungen an alles Sichtbare.
