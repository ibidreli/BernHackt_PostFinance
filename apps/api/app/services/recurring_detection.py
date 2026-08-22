"""Recurring-payment detection (Feature: Zukunftsprognose & Szenario-
Simulation, T3).

Groups normalized transactions (T1) by merchant + category and detects a
rhythm (monthly/quarterly/yearly/irregular) from the gaps between
occurrences. Also detects the salary day from the largest recurring
monthly income.

Kept deliberately simple - no fuzzy matching, no clustering library. See
inline comments for the exact heuristics and their known limitations.
This is detection only, not the fixed-cost vs. outlier classification
(Topf 1/2/3, including the "Rückerstattungen sind kein Einkommen" rule) -
that's T4, built on top of this.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from datetime import date
from statistics import median

from app.models.recurring_payment import AmountHistoryEntry, Interval, RecurringPayment
from app.models.transaction import Transaction

# Representative day-length per interval, used for `is_active`.
_INTERVAL_DAYS = {"monthly": 30, "quarterly": 91, "yearly": 365}

# Gap-length ranges (median days between consecutive occurrences) that
# classify as each interval. Deliberately generous - real billing dates
# jitter by a few days around the "true" period (weekends, bank
# processing, month lengths).
_INTERVAL_RANGES: list[tuple[Interval, range]] = [
    ("monthly", range(25, 36)),
    ("quarterly", range(80, 101)),
    ("yearly", range(340, 391)),
]

MIN_OCCURRENCES = 3
"""Need at least 3 dates (2 gaps) to say anything about a rhythm. Groups
below this are left undetected here - T4 handles them as Topf-3
candidates ("<3 Vorkommen/12 Monate").

Known limitation: at exactly 3 occurrences, a "quarterly" classification
can be coincidence rather than a real rhythm - e.g. three sporadic visits
to the same shop happening to land ~90 days apart. Verified against the
sample data: this does happen (a handful of physical-store merchants get
tagged "quarterly" off 3-8 occurrences). T3 reports what the gaps say;
deciding whether a detected rhythm is trustworthy enough for Topf 1 is a
T4 concern (e.g. cross-checking amount stability, category)."""


def _canonical_merchant_key(merchant: str) -> str:
    """First whitespace token of the extracted merchant name.

    Deliberately simple (no fuzzy matching) - it happens to be exactly
    enough to unify billing-entity variants such as Netflix appearing as
    "NETFLIX.COM LOS GATOS" / "NETFLIX.COM AMSTERDAM" /
    "NETFLIX.COM 866-579-7172" (shared first token "NETFLIX.COM"), while
    still being distinctive for most merchants. Combined with
    category_main as part of the group key (`group_key`) to reduce
    false merges from short/generic first tokens (e.g. "M", "BP", "TCS").

    Known limitation: two genuinely different merchants that share both
    a first token and a category still get merged into one recurring
    payment. Accepted for a hackathon timeline - fixing it properly would
    need amount-similarity clustering, which is exactly the complexity
    "keep it simple" says to avoid here.
    """
    return merchant.split(" ", 1)[0] if merchant else merchant


def group_key(t: Transaction) -> tuple[str, str | None, str]:
    """Public so T4 (`app/services/classification.py`) can map a
    transaction back to the RecurringPayment it belongs to, using the
    exact same grouping logic used to detect it here."""
    return (_canonical_merchant_key(t.merchant), t.category_main, t.flow)


def recurring_payment_id(rp: RecurringPayment) -> str:
    """Stable, unique identifier for a RecurringPayment - used as the
    API-facing `recurring_id` (T7/T8).

    `rp.merchant` alone is NOT unique: verified against real data that 13
    different merchant strings (e.g. "LASTSCHRIFT", "PAYPAL", "MIGROS" -
    generic fallback names, see T1) each label 2-4 *different*
    RecurringPayment groups that only differ by category/flow. Using
    `merchant` alone as an id silently collapsed unrelated recurring
    payments together (found via testing `simulate()`: cancelling Netflix
    also silently removed an unrelated "LASTSCHRIFT" payment). This
    mirrors `group_key`'s tuple exactly, so it's guaranteed unique by
    construction.
    """
    merchant, category_main, flow = (rp.merchant, rp.category_main, rp.flow)
    return f"{merchant}::{category_main or ''}::{flow}"


def _collapse_same_day(transactions: list[Transaction]) -> list[Transaction]:
    """Collapse multiple same-day bookings within a group into one.

    Otherwise e.g. an insurer billing two policy components on the same
    day reads as a 0-day gap and wrecks interval detection. Amounts are
    summed; the first transaction's other fields are kept. Expects
    `transactions` sorted by date.
    """
    by_date: dict[date, list[Transaction]] = defaultdict(list)
    for t in transactions:
        by_date[t.date].append(t)

    collapsed: list[Transaction] = []
    for day, day_txs in sorted(by_date.items()):
        if len(day_txs) == 1:
            collapsed.append(day_txs[0])
        else:
            total = round(sum(t.amount_chf for t in day_txs), 2)
            collapsed.append(day_txs[0].model_copy(update={"amount_chf": total}))
    return collapsed


def _detect_interval(dates: list[date]) -> Interval:
    if len(dates) < MIN_OCCURRENCES:
        return "irregular"
    gaps = [(b - a).days for a, b in zip(dates, dates[1:])]
    gap = median(gaps)
    for interval, day_range in _INTERVAL_RANGES:
        if gap in day_range:
            return interval
    return "irregular"


def _detect_day_of_month(dates: list[date]) -> int | None:
    if not dates:
        return None
    return Counter(d.day for d in dates).most_common(1)[0][0]


def _build_amount_history(transactions: list[Transaction]) -> list[AmountHistoryEntry]:
    """One entry per amount change, in chronological order. Expects
    `transactions` sorted by date. Amounts are stored as positive
    magnitudes regardless of expense/income, matching the API contract's
    convention (`known_payments[].amount_chf`, adjustment amounts)."""
    history: list[AmountHistoryEntry] = []
    last_amount: float | None = None
    for t in transactions:
        amount = round(abs(t.amount_chf), 2)
        if amount != last_amount:
            history.append(AmountHistoryEntry(effective_from=t.date, amount_chf=amount))
            last_amount = amount
    return history


def detect_recurring_payments(
    transactions: list[Transaction],
    reference_date: date | None = None,
) -> list[RecurringPayment]:
    """Group transactions and detect a `RecurringPayment` per group.

    `reference_date` is used for `is_active` ("no booking for 2
    intervals") - defaults to the latest transaction date across all
    transactions, standing in for "today" against a closed CSV export.
    """
    if not transactions:
        return []
    if reference_date is None:
        reference_date = max(t.date for t in transactions)

    groups: dict[tuple[str, str | None, str], list[Transaction]] = defaultdict(list)
    for t in transactions:
        if t.is_transfer:
            continue
        groups[group_key(t)].append(t)

    results: list[RecurringPayment] = []
    for (merchant_key, category_main, flow), group_txs in groups.items():
        group_txs = _collapse_same_day(sorted(group_txs, key=lambda t: t.date))
        if len(group_txs) < MIN_OCCURRENCES:
            continue

        dates = [t.date for t in group_txs]
        interval = _detect_interval(dates)
        day_of_month = _detect_day_of_month(dates) if interval != "irregular" else None
        amount_history = _build_amount_history(group_txs)

        last_seen = dates[-1]
        interval_days = _INTERVAL_DAYS.get(interval, 30)
        is_active = (reference_date - last_seen).days <= 2 * interval_days

        results.append(
            RecurringPayment(
                merchant=merchant_key,
                category_main=category_main,
                category_sub=group_txs[-1].category_sub,
                amount_chf=amount_history[-1].amount_chf,
                interval=interval,
                day_of_month=day_of_month,
                flow=flow,
                first_seen=dates[0],
                last_seen=last_seen,
                is_active=is_active,
                amount_history=amount_history,
            )
        )

    results.sort(key=lambda r: (not r.is_active, r.merchant))
    return results


def detect_salary_recurring(recurring_payments: list[RecurringPayment]) -> RecurringPayment | None:
    """The salary itself: the largest *active* recurring monthly income.

    Simple heuristic (issue: "wiederkehrende Einnahme, gleicher Tag im
    Monat") - salary is reliably the biggest regular paycheck, so
    "largest monthly income" is a safe proxy without needing an explicit
    "this is salary" label anywhere in the source data.

    Only considers `is_active` payments - otherwise a defunct income
    source (e.g. a previous employer) can outrank the real current salary
    just by having been larger while it lasted. Caught against real data:
    the sample CSV has an employer that paid up to CHF 5774.50/month but
    stopped in 2024, while the current, still-active salary tops out
    around CHF 3000-5000 but is smaller on average - naively picking the
    single largest-ever amount would have selected the stale one.

    Returns None if no recurring monthly income was detected - callers
    must fall back to calendar-month behaviour and surface that in the
    UI (issue's "Lohntag nicht erkennbar" edge case), not guess.
    """
    candidates = [
        rp
        for rp in recurring_payments
        if rp.flow == "income"
        and rp.interval == "monthly"
        and rp.day_of_month is not None
        and rp.is_active
    ]
    if not candidates:
        return None
    return max(candidates, key=lambda rp: rp.amount_chf)


def detect_salary_day(recurring_payments: list[RecurringPayment]) -> int | None:
    """`day_of_month` of the detected salary - see `detect_salary_recurring`."""
    salary = detect_salary_recurring(recurring_payments)
    return salary.day_of_month if salary else None
