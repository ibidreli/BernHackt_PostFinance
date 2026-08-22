---
tags: [projekt, design]
---

# Design-System

Quelle: `design/README.md` · Logos unter `design/logos/` · Brand-Referenz: [PostFinance auf Brandfetch](https://brandfetch.com/postfinance.ch)

## Farbpalette

| Farbe | Hex | Verwendung |
|---|---|---|
| PostFinance Yellow | `#FFCC00` | Primärfarbe, Highlights, CTAs |
| PostFinance Green | `#A5C400` | Sekundär-Akzente, positive Zustände |
| Dark Teal | `#005B61` | Text, Navigation, starker Kontrast |
| Light Gray | `#F2F2F2` | Hintergründe, Karten, Trenner |
| White | `#FFFFFF` | Hauptflächen |

## Prinzipien

**Simple** · **Consistent** · **Accessible** (Lesbarkeit, Kontrast) · **Recognizable** (PostFinance-Palette konsequent) · **Functional** (Visuelles dient der Bedienbarkeit). Keine neuen Farben oder Muster ohne klaren funktionalen Zweck.

## Umsetzung im Frontend

In `apps/web/src/styles.css` ist die Palette als Tailwind-4-`@theme`-Tokens auf semantische Namen gemappt (`--color-primary`, `--color-surface`, `--color-foreground`, `--color-border`, `--color-shell`), mit eigenem `:root.dark`-Block. `--color-muted-foreground` und `--color-success` sind pro Theme explizit auf **WCAG-AA-Kontrast** geprüft. Theme-Umschaltung: [[App-Shell & Navigation]].
