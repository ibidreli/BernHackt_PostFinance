---
tags: [frontend]
---

# App-Shell & Navigation

Code: `apps/web/src/app/` · Stack & Konventionen: [[Architektur & Tech-Stack]] · Farben: [[Design-System]]

## Aufbau auf `main`

- `main.ts` → `bootstrapApplication(App, appConfig)`; `app.ts` ist nur ein `<router-outlet />`.
- **`layout/dashboard-layout/`** — die Shell: einklappbare Sidebar, Header mit Toggle, Breadcrumb, Hell/Dunkel-Umschalter, `<main>` mit Router-Outlet. Durchgehend ARIA-Attribute.
- **`layout/sidebar/`** — einklappbare Navigation (`w-64` ↔ `w-[72px]`), Branding "PostFinance Horizons" (der vereinheitlichte Produktname), Nav-Einträge in der Reihenfolge **Prognose → Kategorien → Future Me**. Der frühere Sign-out-Button ist entfernt (es gibt kein Auth). Accessibility: `aria-current`, sr-only-Labels im eingeklappten Zustand.
- **`core/theme.ts`** — `@Service()`-Store auf Signal-Basis: liest `localStorage`, fällt auf `prefers-color-scheme` zurück, toggelt per `effect` die `.dark`-Klasse auf `documentElement`.
- **Routen** (`app.routes.ts`, seit dem Routen-Tausch vom 22.08., [[Sollstatus]]): `''` (Start) → **Prognose** ([[Forecast-Seite]]), `/kategorien` → [[Kategorien-Explorer]], `/future-me` → **Future Me** ([[Assistant-Seite]]); Redirects für alte Links: `forecast` → `/`, `assistant` → `/future-me`, Wildcard → `/`. Das leere `pages/abo-radar/` ist gelöscht. Dazu `core/rail.ts` (rechte Kontextspalte via `ng-template` + Directive), `core/chart-theme.ts` (`chf()`-Formatter), `core/handoff.ts` (consume-once Signal-Store für die Seiten-Verbindungen) und `core/alerts.ts` (Alert-Fetch + client-seitiger Join, [[Alerts]]).
- **Mobile-Fallback für die Rail:** unterhalb `lg` öffnet ein schwebender "Optionen"-Button die Kontextspalte als **Bottom-Sheet** (`max-h` 70dvh, `role="dialog"`, `aria-modal`, Fokus auf dem Schliessen-Button, Escape/Backdrop schliessen, schliesst bei Navigation). Desktop unverändert.

## Angular-Konventionen (aus `apps/web/.claude/CLAUDE.md`)

Verbindlich für alle Beiträge, auch von AI-Agenten:

- **Standalone Components** und **Signals**; `input()`/`output()` statt Decorators; `@Service`-Decorator (Angular 22+).
- Native Control Flow **`@if`/`@for`** statt `*ngIf`/`*ngFor`; **kein `ngClass`/`ngStyle`**.
- Signal Forms; Styling mit Tailwind 4 + daisyUI, semantische Theme-Tokens aus `styles.css`.
- **AXE/WCAG-AA**-Anforderungen an alles Sichtbare.
