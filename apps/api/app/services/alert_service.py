"""Conservative alert detection for the Auffaelligkeiten feature.

The service is deliberately pure: it receives the already-normalized
transactions and Topf classifications from startup and returns stable
Pydantic entities. No HTTP or app.state access here.
"""

from __future__ import annotations

import re
from collections import defaultdict
from datetime import date, timedelta
from statistics import median

from app.core.config import (
    ALERT_DUPLICATE_MIN_CHF,
    ALERT_LOOKBACK_MONTHS,
    ALERT_LARGE_PAYMENT_MIN_CHF,
    ALERT_SPIKE_MIN_DELTA_CHF,
    ALERT_SPIKE_MIN_MONTHS,
    ALERT_SPIKE_MULTIPLIER,
    VARIABLE_BASELINE_MONTHS,
)
from app.models.transaction import Transaction
from app.repositories.transaction_repository import CategoryStats, monthly_category_stats
from app.schemas.alerts import Alert
from app.services.classification import Classification
from app.services.recurring_detection import group_key

_EXPENSE = "expense"
_SLUG_RE = re.compile(r"[^a-z0-9]+")
_DAUERAUFTRAG_RE = re.compile(r"\bDAUERAUFTRAG:\s*(?P<ref>[\w.-]+)", re.IGNORECASE)


def build_alerts(
    transactions: list[Transaction],
    classifications: list[Classification],
) -> list[Alert]:
    """Build all alert types in one deterministic pass."""
    alerts = [
        *_duplicate_charge_alerts(transactions),
        *_large_payment_alerts(classifications),
        *_category_spike_alerts(classifications),
    ]
    alerts = _apply_lookback(alerts, transactions)
    return sorted(alerts, key=_sort_key, reverse=True)


def _is_alertable_expense(t: Transaction) -> bool:
    return t.flow == _EXPENSE and not t.is_transfer


def _amount(t: Transaction) -> float:
    return round(abs(t.amount_chf), 2)


def _slug(value: str | None) -> str:
    cleaned = _SLUG_RE.sub("-", (value or "unknown").lower()).strip("-")
    return cleaned or "unknown"


def _money_slug(amount: float) -> str:
    return f"{amount:.2f}"


def _apply_lookback(alerts: list[Alert], transactions: list[Transaction]) -> list[Alert]:
    if ALERT_LOOKBACK_MONTHS <= 0 or not transactions:
        return alerts
    cutoff = max(t.date for t in transactions) - timedelta(days=ALERT_LOOKBACK_MONTHS * 31)
    cutoff_month = cutoff.strftime("%Y-%m")
    return [
        alert
        for alert in alerts
        if (alert.date is not None and alert.date >= cutoff)
        or (alert.month is not None and alert.month >= cutoff_month)
    ]


def _category_key(t: Transaction) -> tuple[str | None, str | None]:
    return (t.category_main, t.category_sub)


def _category_medians(classifications: list[Classification]) -> dict[tuple[str | None, str | None], float]:
    """Same category population as classification.py after Topf-1 removal.

    The alert decision still reuses c.topf == "outlier"; this is only for
    the explanatory baseline_chf field.
    """
    by_category: dict[tuple[str | None, str | None], list[float]] = defaultdict(list)
    for c in classifications:
        if c.topf == "fixed":
            continue
        by_category[_category_key(c.transaction)].append(_amount(c.transaction))
    return {key: round(median(values), 2) for key, values in by_category.items() if values}


def _duplicate_charge_alerts(transactions: list[Transaction]) -> list[Alert]:
    groups: dict[tuple[date, str, float], list[Transaction]] = defaultdict(list)
    for t in transactions:
        if not _is_alertable_expense(t):
            continue
        amount = _amount(t)
        if amount < ALERT_DUPLICATE_MIN_CHF:
            continue
        merchant_key = group_key(t)[0]
        groups[(t.date, merchant_key, amount)].append(t)

    alerts: list[Alert] = []
    for (day, merchant_key, amount), txs in groups.items():
        if len(txs) < 2:
            continue
        first = sorted(txs, key=lambda t: t.id)[0]
        alerts.append(
            Alert(
                alert_id=f"dup:{day.isoformat()}:{_slug(merchant_key)}:{_money_slug(amount)}",
                type="duplicate_charge",
                severity="danger",
                date=day,
                merchant=first.merchant,
                category_main=first.category_main,
                category_sub=first.category_sub,
                amount_chf=amount,
                count=len(txs),
                booking_text=first.text,
                transaction_id=first.id,
                transaction_ids=[t.id for t in sorted(txs, key=lambda t: t.id)],
            )
        )
    return alerts


def _large_payment_alerts(classifications: list[Classification]) -> list[Alert]:
    medians = _category_medians(classifications)
    recurring_like_ids = _recurring_like_transaction_ids([c.transaction for c in classifications])
    alerts: list[Alert] = []
    for c in classifications:
        t = c.transaction
        amount = _amount(t)
        if (
            c.topf != "outlier"
            or not _is_alertable_expense(t)
            or amount < ALERT_LARGE_PAYMENT_MIN_CHF
            or t.id in recurring_like_ids
        ):
            continue
        alerts.append(
            Alert(
                alert_id=f"large:{t.date.isoformat()}:{_slug(t.merchant_canonical)}:{_money_slug(amount)}:{t.id}",
                type="large_payment",
                severity="warning",
                date=t.date,
                merchant=t.merchant,
                category_main=t.category_main,
                category_sub=t.category_sub,
                amount_chf=amount,
                baseline_chf=medians.get(_category_key(t)),
                booking_text=t.text,
                transaction_id=t.id,
                transaction_ids=[t.id],
            )
        )
    return alerts


def _recurrence_guard_key(t: Transaction) -> tuple[str, ...]:
    match = _DAUERAUFTRAG_RE.search(t.text)
    if match:
        return ("standing_order", match.group("ref"), t.category_main or "", t.flow)
    merchant, category_main, flow = group_key(t)
    return ("merchant", merchant, category_main or "", flow)


def _is_monthly_cadence(dates: list[date]) -> bool:
    if len(dates) < 3:
        return False
    gaps = [(b - a).days for a, b in zip(dates, dates[1:])]
    if not gaps:
        return False
    gap = median(gaps)
    if gap < 25 or gap > 36:
        return False
    in_range = sum(1 for g in gaps if 15 <= g <= 45)
    return in_range / len(gaps) >= 0.8


def _amounts_stable(amounts: list[float]) -> bool:
    if len(amounts) < 3:
        return False
    baseline = median(amounts)
    if baseline <= 0:
        return False
    spread = max(amounts) - min(amounts)
    return max(amounts) <= baseline * 1.25 and spread <= max(100.0, baseline * 0.2)


def _recurring_like_transaction_ids(transactions: list[Transaction]) -> set[str]:
    """Large-payment guard for monthly standing orders that T3 missed.

    Some LASTSCHRIFT/DAUERAUFTRAG exports expose the bank as the merchant
    and the real payee later in the text, so the normal group_key can be
    too coarse and the recurring detector leaves them as outliers. For
    alerts we add a conservative second guard: stable amount, monthly
    cadence, at least 3 occurrences.
    """
    groups: dict[tuple[str, ...], list[Transaction]] = defaultdict(list)
    for t in transactions:
        if _is_alertable_expense(t):
            groups[_recurrence_guard_key(t)].append(t)

    ids: set[str] = set()
    for group in groups.values():
        ordered = sorted(group, key=lambda t: (t.date, t.id))
        if not _is_monthly_cadence([t.date for t in ordered]):
            continue
        if not _amounts_stable([_amount(t) for t in ordered]):
            continue
        ids.update(t.id for t in ordered)
    return ids


def _first_day(year: int, month: int) -> date:
    return date(year, month, 1)


def _month_key(t: Transaction) -> tuple[int, int]:
    return (t.date.year, t.date.month)


def _month_label(month_key: tuple[int, int]) -> str:
    year, month = month_key
    return f"{year:04d}-{month:02d}"


def _category_spike_alerts(classifications: list[Classification]) -> list[Alert]:
    variable_txs = [
        c.transaction
        for c in classifications
        if c.topf == "variable" and _is_alertable_expense(c.transaction)
    ]
    if not variable_txs:
        return []

    totals: dict[tuple[int, int], dict[tuple[str | None, str | None], float]] = defaultdict(
        lambda: defaultdict(float)
    )
    category_txs: dict[
        tuple[tuple[int, int], tuple[str | None, str | None]], list[Transaction]
    ] = defaultdict(list)
    for t in variable_txs:
        month = _month_key(t)
        category = _category_key(t)
        totals[month][category] += _amount(t)
        category_txs[(month, category)].append(t)

    alerts: list[Alert] = []
    for month in sorted(totals):
        as_of = _first_day(*month)
        stats_by_category = {
            (s.category_main, s.category_sub): s
            for s in monthly_category_stats(variable_txs, as_of=as_of, months=VARIABLE_BASELINE_MONTHS)
            if s.months_used >= ALERT_SPIKE_MIN_MONTHS
        }
        for category, raw_total in totals[month].items():
            stats = stats_by_category.get(category)
            if stats is None:
                continue
            total = round(raw_total, 2)
            delta = round(total - stats.median_chf, 2)
            if total < ALERT_SPIKE_MULTIPLIER * stats.median_chf or delta < ALERT_SPIKE_MIN_DELTA_CHF:
                continue
            alerts.append(_spike_alert(month, category, total, stats, category_txs[(month, category)]))
    return alerts


def _spike_alert(
    month: tuple[int, int],
    category: tuple[str | None, str | None],
    total: float,
    stats: CategoryStats,
    transactions: list[Transaction],
) -> Alert:
    category_main, category_sub = category
    ordered = sorted(transactions, key=lambda t: (t.date, t.id))
    return Alert(
        alert_id=f"spike:{_month_label(month)}:{_slug(category_main)}:{_slug(category_sub)}",
        type="category_spike",
        severity="info",
        month=_month_label(month),
        merchant=None,
        category_main=category_main,
        category_sub=category_sub,
        amount_chf=total,
        baseline_chf=stats.median_chf,
        booking_text=ordered[0].text if ordered else None,
        transaction_id=ordered[0].id if ordered else None,
        transaction_ids=[t.id for t in ordered],
    )


def _sort_key(alert: Alert) -> tuple[str, str, str]:
    # Descending outside via reverse-like inverted strings would be clunky;
    # callers get newest first by sorting with this key and reversing.
    primary = alert.date.isoformat() if alert.date else (alert.month or "")
    return (primary, alert.severity, alert.alert_id)
