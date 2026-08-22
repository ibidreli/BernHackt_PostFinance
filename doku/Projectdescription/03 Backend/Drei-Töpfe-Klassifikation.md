---
tags: [backend, algorithmus]
---

# Drei-Töpfe-Klassifikation

Code: `app/services/classification.py`, Schwellwerte in `app/core/config.py` · Kernidee aus [[Issue 4 – Zukunftsprognose]]

## Warum

Die Prognose behandelt Ausgaben nicht als eine Masse, sondern als drei Klassen — **diese Trennung ist der Kern der Genauigkeit**:

| Topf | Klasse | Beispiel | Behandlung im [[Forecast-Service]] |
|---|---|---|---|
| 1 | **fix / bekannt** | Miete, Netflix, Lohn | Teil eines erkannten Rhythmus ([[Recurring-Detection]]) → deterministisch eingeplant, trägt **nichts** zur Bandbreite bei |
| 2 | **regelmässig schwankend** | Lebensmittel, Tanken, Kantine | P25/Median/P75 der letzten 6 Monate pro Kategorie → Erwartungslinie + Band |
| 3 | **einmalig / Ausreisser** | Reisen, Velokauf | **Nicht** in der Basisprognose (sonst sagt die App im Oktober eine zweite Las-Vegas-Reise voraus), aber in `assumptions.excluded_outliers` benannt |

**Reihenfolge zählt:** erst Topf 1 (Rhythmus), dann Ausreisser-Prüfung auf dem Rest, der Überrest ist Topf 2.

## Ausreisser-Regel (kalibriert)

Eine Buchung ist Ausreisser, wenn `Betrag > 3 × Kategorie-Median` **und** `Betrag ≥ CHF 100`, oder wenn die Kategorie < 3 Vorkommen in 12 Monaten hat.

Die zusätzliche absolute Schwelle ist ein gefundener Bug der naiven Issue-Regel: viele Kleinstbeträge (Snacks) drückten den Supermarkt-Median auf CHF 6 — schon ein normaler CHF-40-Wocheneinkauf galt als Ausreisser (237 von 2008 Supermarkt-Buchungen, 12 %). Mit der Doppel-Bedingung: 1 statt 237; gesamt 253 statt 653 Ausreisser.

Ergebnis auf dem Sample-Datensatz: **446 fix · 4604 variabel · 253 Ausreisser** (von 5303).

## Schwellwerte (`app/core/config.py`)

| Konstante | Wert | Bedeutung |
|---|---|---|
| `OUTLIER_MEDIAN_MULTIPLIER` | 3 | Faktor über Kategorie-Median |
| `OUTLIER_MIN_ABSOLUTE_CHF` | 100 | absolute Mindestschwelle |
| `OUTLIER_MIN_OCCURRENCES_12M` | 3 | darunter gilt die Kategorie als "einmalig" |
| `VARIABLE_BASELINE_MONTHS` | 6 | Historie für Median/Perzentile |
| `DEFAULT_BUFFER_CHF` | 0 | Puffer fürs Engpass-Datum |

Alle als plausible Startwerte dokumentiert, gedacht zur Kalibrierung an echten Daten. Bekannte Grenze: der Kategorie-Median wird einmalig über alle Transaktionen (inkl. potenzieller Ausreisser) berechnet, keine iterative Neuberechnung.
