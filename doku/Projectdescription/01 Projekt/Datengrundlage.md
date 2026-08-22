---
tags: [projekt, daten]
---

# Datengrundlage

## Die Mock-Daten

`/data` enthält CSV-Bankexporte im PostFinance-Format:

- **`data_personal.csv`** — der Hauptdatensatz: 5303 Zeilen, ~856 KB, Buchungen bis 21.08.2026. Wird von `docker-compose.yml` als `CSV_PATH` geladen.
- `jeanine_2025_Account1_2025.csv`, `jeanine_2025_Account3_2025.csv` — kleinere Zweitdatensätze (~265 Zeilen).

## CSV-Format

Semikolon-getrennt, `utf-8-sig`:

```
Datum;Avisierungstext;Gutschrift in CHF;Lastschrift in CHF;Label;Kategorie;Valuta;Saldo in CHF
```

- **`Avisierungstext`** ist der rohe Buchungstext — der Merchant muss per Regex-Kaskade extrahiert werden ([[Datenmodell & Repositories]]).
- **`Kategorie`** liegt bereits kategorisiert vor (Format `Gruppe // Unterkategorie`, z. B. `Einkaufen // Supermärkte`) und wird nur eingelesen, nicht berechnet.
- **`Saldo in CHF`** ist bei ~47.7 % der Zeilen leer — der Kontostand zu einem Stichtag muss rekonstruiert werden (letzter bekannter Saldo + Vorwärts-Summierung, `BalanceRepository`).
- Genau eine der Spalten Gutschrift/Lastschrift ist gefüllt → daraus werden Vorzeichen und `flow` (`income`/`expense`) abgeleitet. Zeilen mit beidem oder keinem werden still übersprungen.

## Eigenheiten, die man kennen muss

- **Duplikate sind nicht entscheidbar:** 32 Gruppen exakt identischer Zeilen. Für manche (3× dieselbe SBB-Zahlung) wäre Löschen richtig, für mindestens eine (2× "OXYMORON BAAR") beweist die Saldo-Rekonstruktion, dass beide real sind. Dedup wurde deshalb **bewusst verworfen**.
- **Sub-Tages-Reihenfolge ist nicht rekonstruierbar** (weder Dateireihenfolge noch `Valuta` sind zuverlässig). Der Vertrag ist Tages-Granularität — dort ist die Saldo-Rekonstruktion verifiziert exakt (1312/1312 Checkpoints, 0 Abweichungen).
- **Keine echten Quartals-/Jahresmuster:** Der Datensatz enthält keinen 13. Monatslohn-Sprung, keine saubere Quartalsrechnung, und die Steuerzahlungen sind chaotisch (CHF 20–2500, Abstände 7–330 Tage). Das Akzeptanzkriterium "Jahresansicht zeigt Steuertermine & 13. Monatslohn" aus [[Issue 4 – Zukunftsprognose]] ist mit diesen Daten **nicht erfüllbar** — dokumentierte Datenlücke, kein Code-Fehler.
- Fremdwährung: `exchange_rate = 1.0` auch bei EUR-Buchungen (relevant für [[Kategorien-Explorer]]).
- 3 Zeilen ohne Kategorie werden auf `None` gemappt.

## Verwandt

[[Datenmodell & Repositories]] · [[Recurring-Detection]] · [[Projektstatus]]
