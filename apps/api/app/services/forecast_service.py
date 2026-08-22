"""Forecast service (T7): the feature's core. Pure functions, no HTTP
dependency (Feature 3 / the chatbot calls this directly per the issue) -
callers pass in already-loaded transactions/recurring_payments/
classifications/balance_repo explicitly rather than reaching into
`app.state` themselves.

Lohnperioden statt Kalendermonate: `horizon="next_salary"` resolves to
the real next salary date (from `detect_salary_recurring`, T3), and every
recurring payment is projected forward from its own detected rhythm
(`RecurringPayment.last_seen` + interval), not reset at calendar-month
boundaries - so a "13. Monatslohn im Dezember" or a quarterly BKW bill
shows up on its actual date, not smoothed away.

Drei Töpfe (T4) feed in as: Topf 1 ("fixed") RecurringPayments with a
detected rhythm get projected as deterministic `known_payments` and
contribute zero band width. Topf 2 ("variable") transactions feed
`monthly_category_stats` (T5) for the P25/median/P75 band. Topf 3
("outlier") transactions are excluded entirely, surfaced only in
`assumptions.excluded_outliers`.

Band construction (simplification, documented): each category's monthly
P25/median/P75 (T5) is summed across categories into one aggregate
monthly rate, then divided by ~30.44 into a daily rate that accumulates
linearly over the horizon. This assumes categories are independent and
ignores correlation between them - a real joint-distribution model is out
of scope for a hackathon timeline; summing per-category percentiles is
the standard simplification here (mirrors how the issue itself describes
the median as computed "pro Kategorie" and implies aggregation).
"""

from __future__ import annotations

import calendar
from collections import defaultdict
from datetime import date, timedelta
from typing import Literal, NamedTuple

from app.core.config import DEFAULT_BUFFER_CHF, VARIABLE_BASELINE_MONTHS
from app.models.recurring_payment import AmountHistoryEntry, RecurringPayment
from app.models.transaction import Transaction
from app.repositories.balance_repository import BalanceRepository
from app.repositories.transaction_repository import monthly_category_stats
from app.schemas.forecast import (
    AddRecurring,
    AdjustRecurring,
    Adjustment,
    Assumptions,
    CancelRecurring,
    Diff,
    DiffPoint,
    ForecastResponse,
    FreeToSpend,
    Horizon,
    KnownPayment,
    NextSalary,
    OneOff,
    SeriesPoint,
    SimulateResponse,
    TightDate,
)
from app.services.classification import Classification
from app.services.recurring_detection import detect_salary_recurring, recurring_payment_id

_DAYS_PER_MONTH = 30.44  # 365.25 / 12
_HORIZON_DAYS = {"30d": 30, "90d": 90, "365d": 365}
_INTERVAL_STEP_MONTHS = {"monthly": 1, "quarterly": 3, "yearly": 12}
_INTERVAL_MONTHLY_FACTOR = {"monthly": 1.0, "quarterly": 1 / 3, "yearly": 1 / 12}


class NoBalanceAvailableError(Exception):
    """Issue's "Kein Saldo vorhanden" edge case: no balance (real or
    reconstructible) is available as of the requested date. The API layer
    (T10) should catch this and prompt for a manually entered starting
    balance, not show an empty chart."""

    def __init__(self, as_of: date):
        self.as_of = as_of
        super().__init__(f"No balance available as of {as_of}")


class _DatedEvent(NamedTuple):
    """A single dated cash-flow event feeding the series/known_payments -
    either a projected RecurringPayment occurrence or a one-off."""

    date: date
    label: str
    amount_chf: float  # positive magnitude
    flow: Literal["expense", "income"]
    category: str | None
    recurring_id: str | None


class _ScenarioOverrides(NamedTuple):
    """Internal: what `simulate()` swaps in for the scenario forecast, on
    top of the unchanged baseline `recurring_payments`."""

    recurring_payments: list[RecurringPayment]
    cancel_from: dict[str, date]
    one_off_events: list[_DatedEvent]


# --- date helpers ---------------------------------------------------------


def _clamp_date(year: int, month: int, day: int) -> date:
    last_day = calendar.monthrange(year, month)[1]
    return date(year, month, min(day, last_day))


def _step_months(d: date, months: int) -> date:
    month_index = d.month - 1 + months
    year = d.year + month_index // 12
    month = month_index % 12 + 1
    return _clamp_date(year, month, d.day)


def _next_salary_date(as_of: date, salary_day: int) -> date:
    candidate = _clamp_date(as_of.year, as_of.month, salary_day)
    if candidate <= as_of:
        nxt = _step_months(candidate, 1)
        candidate = _clamp_date(nxt.year, nxt.month, salary_day)
    return candidate


def _resolve_horizon_end(as_of: date, horizon: Horizon, salary_date: date | None) -> date:
    if horizon == "next_salary":
        if salary_date is not None:
            return salary_date
        # Issue: "Fallback auf Kalendermonat, im UI benannt. Nicht still
        # auf den 1. raten." - end of the current calendar month is the
        # named fallback; `assumptions.salary_day_detected=False` is what
        # tells the UI to name it.
        return _clamp_date(as_of.year, as_of.month, 31)
    return as_of + timedelta(days=_HORIZON_DAYS[horizon])


# --- recurring-payment projection ------------------------------------


def _project_occurrences(
    rp: RecurringPayment, start: date, end: date, cancel_from: date | None = None
) -> list[date]:
    """Future occurrence dates within [start, end], stepped forward from
    `rp.last_seen` on the RecurringPayment's own detected rhythm - not
    reset at calendar-month boundaries (Lohnperioden principle)."""
    step = _INTERVAL_STEP_MONTHS.get(rp.interval)
    if step is None:  # "irregular" - not projectable, T4 already excludes these from Topf 1
        return []

    occ = rp.last_seen
    while occ < start:
        occ = _step_months(occ, step)

    occurrences: list[date] = []
    while occ <= end:
        if cancel_from is not None and occ >= cancel_from:
            break
        occurrences.append(occ)
        occ = _step_months(occ, step)
    return occurrences


def _format_category(main: str | None, sub: str | None) -> str | None:
    if main and sub:
        return f"{main} // {sub}"
    return main or sub


def _known_events(
    recurring_payments: list[RecurringPayment],
    start: date,
    end: date,
    cancel_from: dict[str, date] | None = None,
) -> list[_DatedEvent]:
    cancel_from = cancel_from or {}
    events: list[_DatedEvent] = []
    for rp in recurring_payments:
        if not rp.is_active:
            continue
        rp_id = recurring_payment_id(rp)
        cutoff = cancel_from.get(rp_id)
        for occ in _project_occurrences(rp, start, end, cancel_from=cutoff):
            events.append(
                _DatedEvent(
                    date=occ,
                    label=rp.merchant,
                    amount_chf=rp.amount_chf,
                    flow=rp.flow,
                    category=_format_category(rp.category_main, rp.category_sub),
                    recurring_id=rp_id,
                )
            )
    return events


# --- Topf-2 baseline (T5) --------------------------------------------


def _variable_daily_rates(
    classifications: list[Classification], as_of: date
) -> tuple[float, float, float, int]:
    """(daily_median, daily_p25, daily_p75, months_used)."""
    variable_txs = [c.transaction for c in classifications if c.topf == "variable"]
    stats = monthly_category_stats(variable_txs, as_of=as_of, months=VARIABLE_BASELINE_MONTHS)
    if not stats:
        return 0.0, 0.0, 0.0, 0

    months_used = stats[0].months_used
    total_median = sum(s.median_chf for s in stats)
    total_p25 = sum(s.p25_chf for s in stats)
    total_p75 = sum(s.p75_chf for s in stats)

    if months_used < 3:
        # Issue edge case: "Unter 3 Monaten: Prognose ohne Band, mit
        # Hinweis" - collapse the band to a line rather than show a
        # meaningless P25/P75 computed from 1-2 data points.
        rate = total_median / _DAYS_PER_MONTH
        return rate, rate, rate, months_used

    return (
        total_median / _DAYS_PER_MONTH,
        total_p25 / _DAYS_PER_MONTH,
        total_p75 / _DAYS_PER_MONTH,
        months_used,
    )


def _excluded_outliers(
    classifications: list[Classification], as_of: date, months: int
) -> list[str]:
    cutoff = as_of - timedelta(days=months * 31)
    merchants = {
        c.transaction.merchant
        for c in classifications
        if c.topf == "outlier" and c.transaction.date >= cutoff
    }
    return sorted(merchants)


# --- series + tight_date -----------------------------------------------


def _build_series(
    opening_balance: float,
    as_of: date,
    horizon_end: date,
    events: list[_DatedEvent],
    daily_median: float,
    daily_p25: float,
    daily_p75: float,
    resolution_days: int,
    buffer_chf: float,
    salary_day: int | None,
) -> tuple[list[SeriesPoint], TightDate | None]:
    events_by_date: dict[date, float] = defaultdict(float)
    for e in events:
        signed = e.amount_chf if e.flow == "income" else -e.amount_chf
        events_by_date[e.date] += signed

    points: list[SeriesPoint] = []
    tight: TightDate | None = None
    cum_known = 0.0
    d = as_of
    while True:
        cum_known += events_by_date.get(d, 0.0)
        elapsed = (d - as_of).days
        var_expected = daily_median * elapsed
        var_lower = daily_p75 * elapsed  # pessimistic = spends more (P75) -> lower balance
        var_upper = daily_p25 * elapsed  # optimistic = spends less (P25) -> higher balance
        expected = opening_balance + cum_known - var_expected
        lower = opening_balance + cum_known - var_lower
        upper = opening_balance + cum_known - var_upper

        if tight is None and lower < buffer_chf:
            # Issue: computed from the pessimistic (lower) curve on
            # purpose - "eine Warnung, die zu spät kommt, ist wertlos".
            # days_before_salary uses the *next* salary date after the
            # tight_date itself, not the one from `as_of` - for horizons
            # longer than "next_salary", the tight_date can fall after
            # the upcoming payday, and the relevant reference point is
            # "how many days before the salary that actually follows the
            # squeeze", matching the issue's own phrasing ("vier Tage vor
            # deinem Lohn"). Found via testing: using the as_of-relative
            # salary date here produced negative day counts.
            days_before_salary = (
                (_next_salary_date(d, salary_day) - d).days if salary_day is not None else None
            )
            tight = TightDate(
                date=d,
                days_until=elapsed,
                days_before_salary=days_before_salary,
                projected_balance_chf=round(lower, 2),
            )

        if elapsed % resolution_days == 0 or d == horizon_end:
            points.append(
                SeriesPoint(
                    date=d,
                    expected_chf=round(expected, 2),
                    lower_chf=round(lower, 2),
                    upper_chf=round(upper, 2),
                )
            )

        if d == horizon_end:
            break
        d += timedelta(days=1)

    return points, tight


# --- GET /forecast --------------------------------------------------


def forecast(
    transactions: list[Transaction],
    recurring_payments: list[RecurringPayment],
    classifications: list[Classification],
    balance_repo: BalanceRepository,
    horizon: Horizon = "next_salary",
    as_of: date | None = None,
    buffer_chf: float = DEFAULT_BUFFER_CHF,
    _scenario: _ScenarioOverrides | None = None,
) -> ForecastResponse:
    """Baseline forecast (or, internally, a scenario forecast when called
    by `simulate()` via `_scenario`). Raises `NoBalanceAvailableError` if
    no balance is available as of `as_of` - see issue's "Kein Saldo
    vorhanden" edge case.
    """
    if as_of is None:
        as_of = date.today()

    opening = balance_repo.as_of(as_of)
    if opening is None:
        raise NoBalanceAvailableError(as_of)

    effective_recurring = _scenario.recurring_payments if _scenario else recurring_payments
    cancel_from = _scenario.cancel_from if _scenario else {}
    one_off_events = _scenario.one_off_events if _scenario else []

    salary_rp = detect_salary_recurring(effective_recurring)
    salary_date = _next_salary_date(as_of, salary_rp.day_of_month) if salary_rp else None
    horizon_end = _resolve_horizon_end(as_of, horizon, salary_date)

    events = _known_events(effective_recurring, as_of, horizon_end, cancel_from=cancel_from)
    events += [e for e in one_off_events if as_of <= e.date <= horizon_end]

    daily_median, daily_p25, daily_p75, months_used = _variable_daily_rates(classifications, as_of)
    resolution_days = 7 if horizon == "365d" else 1

    series, tight_date = _build_series(
        opening.balance_chf,
        as_of,
        horizon_end,
        events,
        daily_median,
        daily_p25,
        daily_p75,
        resolution_days,
        buffer_chf,
        salary_rp.day_of_month if salary_rp else None,
    )

    known_payments = [
        KnownPayment(
            date=e.date,
            label=e.label,
            amount_chf=e.amount_chf,
            category=e.category,
            recurring_id=e.recurring_id,
        )
        for e in sorted(events, key=lambda e: e.date)
    ]

    notes: list[str] = []
    if salary_rp is None:
        notes.append("Lohntag nicht erkennbar - Fallback auf Kalendermonat.")
    if 0 < months_used < VARIABLE_BASELINE_MONTHS:
        notes.append(f"Nur {months_used} Monate Historie verfügbar statt {VARIABLE_BASELINE_MONTHS}.")
    if months_used < 3:
        notes.append("Weniger als 3 Monate Historie - Prognose ohne Band (P25 = P75 = Median).")

    assumptions = Assumptions(
        variable_baseline_method=f"median_{months_used}m",
        band_method="p25_p75" if months_used >= 3 else "none",
        excluded_outliers=_excluded_outliers(classifications, as_of, VARIABLE_BASELINE_MONTHS),
        interest_applied=False,
        salary_day_detected=salary_rp is not None,
        variable_baseline_months_used=months_used,
        notes=notes,
    )

    last = series[-1]
    return ForecastResponse(
        as_of=as_of,
        horizon=horizon,
        horizon_end=horizon_end,
        opening_balance_chf=opening.balance_chf,
        next_salary=NextSalary(date=salary_date, amount_chf=salary_rp.amount_chf) if salary_rp else None,
        free_to_spend=FreeToSpend(
            expected_chf=last.expected_chf, lower_chf=last.lower_chf, upper_chf=last.upper_chf
        ),
        tight_date=tight_date,
        known_payments=known_payments,
        series=series,
        assumptions=assumptions,
    )


# --- POST /forecast/simulate ------------------------------------------


def _apply_adjustments(
    recurring_payments: list[RecurringPayment],
    adjustments: list[Adjustment],
) -> _ScenarioOverrides:
    """Pure function: never mutates `recurring_payments` (Pydantic models
    are copied via `.model_copy()`). Unknown `recurring_id`s are silently
    ignored rather than raising - a typo'd id shouldn't crash a live demo;
    the resulting scenario just won't differ from baseline for that one
    adjustment.
    """
    result: dict[str, RecurringPayment] = {recurring_payment_id(rp): rp for rp in recurring_payments}
    cancel_from: dict[str, date] = {}
    one_offs: list[_DatedEvent] = []

    for adj in adjustments:
        if isinstance(adj, CancelRecurring):
            if adj.recurring_id not in result:
                continue
            if adj.effective_from is None:
                del result[adj.recurring_id]
            else:
                cancel_from[adj.recurring_id] = adj.effective_from

        elif isinstance(adj, AdjustRecurring):
            rp = result.get(adj.recurring_id)
            if rp is None:
                continue
            result[adj.recurring_id] = rp.model_copy(
                update={"amount_chf": round(rp.amount_chf + adj.delta_chf, 2)}
            )

        elif isinstance(adj, AddRecurring):
            new_rp = RecurringPayment(
                merchant=adj.label,
                category_main="Simulation",
                category_sub=None,
                amount_chf=adj.amount_chf,
                interval=adj.interval,
                day_of_month=adj.start_date.day,
                flow="expense",
                first_seen=adj.start_date,
                last_seen=adj.start_date,
                is_active=True,
                amount_history=[
                    AmountHistoryEntry(effective_from=adj.start_date, amount_chf=adj.amount_chf)
                ],
            )
            result[recurring_payment_id(new_rp)] = new_rp

        elif isinstance(adj, OneOff):
            # amount_chf is a positive expense magnitude, matching the
            # issue's own example ("Auto", amount_chf: 30000.00 - a cost,
            # not income) and RecurringPayment/KnownPayment's convention.
            # Found via testing: an earlier sign-inference version
            # ("positive = income") made a CHF 30'000 car purchase
            # *increase* the projected balance.
            one_offs.append(
                _DatedEvent(
                    date=adj.date,
                    label=adj.label,
                    amount_chf=abs(adj.amount_chf),
                    flow="expense",
                    category="Simulation",
                    recurring_id=None,
                )
            )

    return _ScenarioOverrides(
        recurring_payments=list(result.values()), cancel_from=cancel_from, one_off_events=one_offs
    )


def _monthly_equivalent_impact(
    adjustments: list[Adjustment], baseline_recurring: list[RecurringPayment]
) -> float:
    """Net monthly-equivalent recurring impact of all adjustments
    combined, in "scenario minus baseline" terms: positive = the scenario
    keeps/frees up more money per month. One-offs don't contribute (not
    recurring).

    Sign convention note: the issue's own example JSON shows
    `"monthly_chf": -20.90` for what reads like a Netflix-cancel scenario,
    i.e. framed as "the cost that disappeared" rather than "the balance
    improvement". We use the opposite (positive = improvement) because it
    matches the UI copy elsewhere in the issue ("Nach 1 Jahr: CHF 251
    mehr") and `tight_date_shift_days` (positive = more buffer) - keeping
    one consistent "positive = better" convention throughout `diff`
    beats matching one ambiguous example number.
    """
    by_id = {recurring_payment_id(rp): rp for rp in baseline_recurring}
    impact = 0.0
    for adj in adjustments:
        if isinstance(adj, CancelRecurring):
            rp = by_id.get(adj.recurring_id)
            if rp is None:
                continue
            factor = _INTERVAL_MONTHLY_FACTOR.get(rp.interval, 0.0)
            sign = 1 if rp.flow == "expense" else -1
            impact += sign * rp.amount_chf * factor
        elif isinstance(adj, AdjustRecurring):
            rp = by_id.get(adj.recurring_id)
            if rp is None:
                continue
            factor = _INTERVAL_MONTHLY_FACTOR.get(rp.interval, 0.0)
            sign = -1 if rp.flow == "expense" else 1
            impact += sign * adj.delta_chf * factor
        elif isinstance(adj, AddRecurring):
            factor = _INTERVAL_MONTHLY_FACTOR.get(adj.interval, 0.0)
            impact += -1 * adj.amount_chf * factor
    return round(impact, 2)


def simulate(
    transactions: list[Transaction],
    recurring_payments: list[RecurringPayment],
    classifications: list[Classification],
    balance_repo: BalanceRepository,
    adjustments: list[Adjustment],
    horizon: Horizon = "next_salary",
    as_of: date | None = None,
    buffer_chf: float = DEFAULT_BUFFER_CHF,
) -> SimulateResponse:
    baseline = forecast(
        transactions, recurring_payments, classifications, balance_repo, horizon, as_of, buffer_chf
    )
    overrides = _apply_adjustments(recurring_payments, adjustments)
    scenario = forecast(
        transactions,
        recurring_payments,
        classifications,
        balance_repo,
        horizon,
        as_of,
        buffer_chf,
        _scenario=overrides,
    )

    # Assumes baseline/scenario series share the same dates, true whenever
    # an adjustment doesn't touch the salary itself (true for all three
    # demo presets and the documented one_off use case) - see simulate()
    # module docs for the general case.
    diff_points = [
        DiffPoint(date=s.date, diff_chf=round(s.expected_chf - b.expected_chf, 2))
        for b, s in zip(baseline.series, scenario.series)
    ]
    total_at_horizon = round(scenario.series[-1].expected_chf - baseline.series[-1].expected_chf, 2)

    tight_shift = None
    if baseline.tight_date and scenario.tight_date:
        tight_shift = (scenario.tight_date.date - baseline.tight_date.date).days

    diff = Diff(
        monthly_chf=_monthly_equivalent_impact(adjustments, recurring_payments),
        cumulative_series=diff_points,
        total_at_horizon_chf=total_at_horizon,
        tight_date_shift_days=tight_shift,
    )
    return SimulateResponse(baseline=baseline, scenario=scenario, diff=diff)
