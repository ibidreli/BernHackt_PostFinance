"""Saldo-Repository (T6): Saldo per Stichtag.

Keine separate Speicherung nötig - jede Transaktion trägt bereits den
Saldo direkt nach der Buchung (`Transaction.balance_chf`, aus der CSV-
Spalte "Saldo in CHF", siehe T1). Wie `TransactionRepository`: kein
DB-Zugriff, arbeitet auf einer bereits geladenen, chronologisch
sortierten Transaktionsliste.

Wichtig, gegen echte Daten geprüft: in `data_personal.csv` ist "Saldo in
CHF" bei **47.7 % der Zeilen leer** (2530 von 5303) - offenbar trägt bei
mehreren Buchungen am selben Tag nur eine davon den Saldo. Naiv "die
letzte Buchung mit Saldo vor `as_of` nehmen" kann deshalb einen veralteten
Wert liefern, wenn dazwischen Buchungen ohne eigenen Saldo lagen. Der
Fix: letzten *bekannten* Saldo suchen, dann die Beträge aller Buchungen
seither aufsummieren.

Verifiziert auf Tages-Granularität - genau das, was `as_of(date)` per
Signatur verspricht: für alle 1312 Kalendertage mit einem tatsächlich
verzeichneten Saldo reproduziert `as_of(dieser_tag)` diesen exakt
(0 Abweichungen). Bewusst NICHT verifiziert (und nicht verifizierbar) auf
Sub-Tages-Ebene: `Datum`/`Valuta` liefern keine verlässliche Reihenfolge
für mehrere Buchungen am selben Tag (Valuta kann vor Datum liegen, siehe
Sortierung in `transaction_repository.py`), wodurch ein Saldo unmittelbar
nach einer *einzelnen* Buchung mitten am Tag falsch sein kann. Das
betrifft aber nicht den hier eingehaltenen Vertrag (`date`, keine
Uhrzeit) - für Tagesabschluss-Salden ist die Rekonstruktion exakt.
"""

from __future__ import annotations

import bisect
import math
from datetime import date

from app.models.balance import Balance
from app.models.transaction import Transaction


class BalanceRepository:
    def __init__(self, transactions: list[Transaction]):
        # Muss chronologisch sortiert sein - T1 (`normalize_transactions`)
        # garantiert das, hier nicht nochmal sortiert um O(n log n) pro
        # Request zu sparen.
        self._transactions = transactions

    def as_of(self, as_of: date) -> Balance | None:
        """Saldo am Stichtag `as_of`, rekonstruiert falls nötig (siehe
        Modul-Docstring). Liegt `as_of` nach der letzten bekannten Buchung
        (z. B. "heute", CSV endet gestern), wird trotzdem die letzte
        bekannte Buchung verwendet - mehr Information gibt es nicht.

        `None`, wenn vor `as_of` gar kein Saldo bekannt ist (weder direkt
        noch rekonstruierbar) - siehe Issue-Edge-Case "Kein Saldo
        vorhanden": der Aufrufer muss dann auf einen manuell eingegebenen
        Startsaldo zurückfallen (`Balance(source="manual")`), nicht raten.
        """
        idx = bisect.bisect_right(self._transactions, as_of, key=lambda t: t.date)
        if idx == 0:
            return None

        anchor_i = next(
            (i for i in range(idx - 1, -1, -1) if not math.isnan(self._transactions[i].balance_chf)),
            None,
        )
        if anchor_i is None:
            return None

        anchor = self._transactions[anchor_i]
        carried_forward = sum(t.amount_chf for t in self._transactions[anchor_i + 1 : idx])
        return Balance(
            as_of=as_of,
            balance_chf=round(anchor.balance_chf + carried_forward, 2),
            source="transaction",
        )

    def latest(self) -> Balance | None:
        """Der zuletzt bekannte Saldo insgesamt - z. B. als Default-
        Startsaldo, wenn keine explizite `as_of` angegeben ist."""
        if not self._transactions:
            return None
        return self.as_of(self._transactions[-1].date)
