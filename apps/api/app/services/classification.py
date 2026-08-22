"""Drei-Topf-Klassifikation (T4): jede Transaktion wird einem von drei
Töpfen zugeordnet - das ist laut Issue der Kern der Prognose-Genauigkeit.
Baut auf der Recurring-Payment-Erkennung (T3) für Topf 1 auf und auf
Kategorie-Statistik für Topf 2/3.

    Topf 1 "fixed"    - Teil einer RecurringPayment mit erkanntem
                        Rhythmus (monthly/quarterly/yearly, aus T3).
                        Datum und Betrag bekannt -> deterministisch.
    Topf 2 "variable" - alles andere, was nicht als Ausreisser gilt.
                        Median der letzten N Monate pro Kategorie -> Band
                        (Berechnung selbst folgt in T5).
    Topf 3 "outlier"  - Betrag > 3x Kategorie-Median UND über einer
                        absoluten Mindestschwelle (siehe unten), ODER
                        Kategorie mit weniger als 3 Vorkommen in den
                        letzten 12 Monaten. Fällt komplett aus der
                        Basisprognose raus.

Reihenfolge ist wichtig: Topf 1 wird zuerst bestimmt (über T3), erst
danach Topf 3 auf dem Rest - der verbleibende Rest ist Topf 2. Eine
Transaktion, die Teil eines erkannten Rhythmus ist, kann nie gleichzeitig
Ausreisser sein. Das deckt genau die Issue-Ausnahme ab ("bekannte
unregelmässige Fixkosten mit klarem Rhythmus wie Steuern, BKW, 13.
Monatslohn gehören in Topf 1, nicht in Topf 3"), ohne Kategorienamen hart
zu codieren - der Rhythmus allein entscheidet.

Wichtig, gegen echte Daten geprüft: nicht jede intuitiv "fixe" Kategorie
landet deshalb in Topf 1. Die Krankenkasse (CSS) im Sample-Datensatz hat
sowohl schwankende Beträge als auch schwankende Daten (siehe T3-Fund) und
wird deshalb korrekt zu Topf 2 (nicht Topf 1, nicht Topf 3) - eine
bewusste, datengetriebene Entscheidung statt eines hartcodierten
Kategorie-Overrides ("Krankenkasse ist immer Topf 1"), passend zum
Issue-Prinzip "aus der Historie erkannt, nicht hart codiert".
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta
from statistics import median
from typing import Literal, NamedTuple

from app.core.config import (
    OUTLIER_MEDIAN_MULTIPLIER,
    OUTLIER_MIN_ABSOLUTE_CHF,
    OUTLIER_MIN_OCCURRENCES_12M,
)
from app.models.recurring_payment import RecurringPayment
from app.models.transaction import Transaction
from app.services.recurring_detection import group_key

Topf = Literal["fixed", "variable", "outlier"]
CategoryKey = tuple[str | None, str | None]  # (category_main, category_sub)


class Classification(NamedTuple):
    transaction: Transaction
    topf: Topf
    recurring_payment: RecurringPayment | None = None
    """Set when topf == "fixed": the RecurringPayment this booking belongs to."""


def _category_key(t: Transaction) -> CategoryKey:
    return (t.category_main, t.category_sub)


def classify_transactions(
    transactions: list[Transaction],
    recurring_payments: list[RecurringPayment],
    reference_date: date | None = None,
) -> list[Classification]:
    """Classify every transaction into Topf 1/2/3, in the original order.

    `reference_date` anchors the "< 3 Vorkommen in 12 Monaten" check -
    defaults to the latest transaction date (same convention as T3).

    Simplification: the category median used for the outlier check is
    computed once over *all* non-fixed transactions in that category,
    including any outliers themselves - no iterative re-computation.
    Medians are robust to a single extreme value, so this is close
    enough for a hackathon timeline; a category with many genuine
    outliers could still skew its own threshold.
    """
    if not transactions:
        return []
    if reference_date is None:
        reference_date = max(t.date for t in transactions)

    # --- Topf 1: same grouping key T3 used to detect the rhythm ---
    fixed_lookup: dict[tuple[str, str | None, str], RecurringPayment] = {
        (rp.merchant, rp.category_main, rp.flow): rp
        for rp in recurring_payments
        if rp.interval != "irregular"
    }
    is_fixed = [group_key(t) in fixed_lookup for t in transactions]
    remaining = [t for t, fixed in zip(transactions, is_fixed) if not fixed]

    # --- category stats over the remainder, for Topf 2 vs. Topf 3 ---
    window_start = reference_date - timedelta(days=365)
    by_category: dict[CategoryKey, list[Transaction]] = defaultdict(list)
    for t in remaining:
        by_category[_category_key(t)].append(t)

    category_median = {
        key: median(abs(t.amount_chf) for t in txs) for key, txs in by_category.items()
    }
    category_occurrences_12m = {
        key: sum(1 for t in txs if t.date >= window_start) for key, txs in by_category.items()
    }

    classifications: list[Classification] = []
    for t, fixed in zip(transactions, is_fixed):
        if fixed:
            classifications.append(Classification(t, "fixed", fixed_lookup[group_key(t)]))
            continue

        key = _category_key(t)
        cat_median = category_median[key]
        amount = abs(t.amount_chf)
        is_outlier = category_occurrences_12m[key] < OUTLIER_MIN_OCCURRENCES_12M or (
            cat_median > 0
            and amount > OUTLIER_MEDIAN_MULTIPLIER * cat_median
            and amount >= OUTLIER_MIN_ABSOLUTE_CHF
        )
        classifications.append(Classification(t, "outlier" if is_outlier else "variable"))

    return classifications
