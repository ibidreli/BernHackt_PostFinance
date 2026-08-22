---
tags: [backend]
---

# Datenmodell & Repositories

Rohdaten: [[Datengrundlage]] · Konsumenten: [[Recurring-Detection]], [[Drei-Töpfe-Klassifikation]], [[Forecast-Service]]

## Domain-Modelle (`app/models/`)

Pydantic-Modelle ohne DB-Keys (es gibt keine DB): `transaction.py`, `balance.py`, `recurring_payment.py`. `RecurringPayment` trägt `merchant`, `category_main`, `amount_chf` (aktuell), `interval` (`monthly|quarterly|yearly|irregular`), `day_of_month`, `flow`, `first_seen`/`last_seen`, `is_active`, `amount_history` (ein Eintrag pro Preisänderung — die Grundlage des [[Abo-Radar]]s). Bewusste Abweichung vom Issue: `amount_chf` ist `float` statt `Decimal` — Konsistenz mit der pandas-Pipeline war wichtiger; Rundungsrisiko bei 2 Nachkommastellen vernachlässigbar.

## TransactionRepository (`app/repositories/transaction_repository.py`)

**Merchant-Extraktion als Regex-Kaskade** über den `Avisierungstext` — regelbasiert, kein ML:

1. Kartenzahlung `KARTEN NR. XXXX####`
2. TWINT `TELEFON-NR.` (konsumierender Regex — ein Greedy-Regex liess bei `GELD SENDEN` die Empfänger-Telefonnummer im Namen stehen; gefixt)
3. `LASTSCHRIFT <IBAN>`
4. `AUFTRAGGEBER:` / `ABSENDER:` / `ZAHLUNGSEMPFÄNGER:`
5. `PREIS FÜR`
6. generischer `VOM <datum>`-Fallback (~9–10 % der Zeilen)

Bekannte Grenze: ~15 Zeilen (0.3 %), wo bei `LASTSCHRIFT` eine vermittelnde Bank vor der IBAN steht → Extraktion liefert die Bank statt des Empfängers. Merchant-Varianten (3× Netflix-Schreibweisen) werden hier **nicht** kanonisiert — nur für die Gruppierung in der [[Recurring-Detection]] gelöst.

Ausserdem: Kategorie-Split an `//` (`category_main` / `category_sub`), signierter Betrag + `flow` aus Gutschrift/Lastschrift, chronologische Sortierung (Fix: Liste vor dem stabilen Sort umkehren, damit gleiche Tage chronologisch landen).

**`monthly_category_stats()`** liefert P25/Median/P75 der Monatssummen pro Kategorie über die letzten N **vollen** Kalendermonate (laufender Monat ausgeschlossen, Null-Monate zählen mit) — die statistische Basis für das Prognose-Band.

## BalanceRepository (`app/repositories/balance_repository.py`)

`as_of(date)` rekonstruiert den Kontostand: letzter bekannter `Saldo in CHF` (47.7 % der Zeilen sind leer) plus Vorwärts-Summierung der Transaktionen. Auf Tages-Granularität verifiziert exakt: 1312/1312 Kalendertage mit echtem Saldo-Checkpoint, 0 Abweichungen. Wirft `NoBalanceAvailableError` → HTTP 409 in der [[API-Referenz]].
