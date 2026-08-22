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
monthly figure. This assumes categories are independent and ignores
correlation between them - a real joint-distribution model is out of
scope for a hackathon timeline; summing per-category percentiles is the
standard simplification here (mirrors how the issue itself describes the
median as computed "pro Kategorie" and implies aggregation).

The *expected* line accumulates linearly over the horizon (monthly median
x months elapsed - expected spend really does scale with time). The
*band width* around it does not: it scales with sqrt(months elapsed),
not months elapsed, so it doesn't assume every month re-hits its most
extreme P25/P75 value independently (12 bad months in a row). This is
the standard variance-of-a-sum-of-independent-periods argument (CLT) and
was added after testing showed linear growth made the 365d band
implausibly wide (~CHF 15'000 span) - see `_build_series` for the exact
formula and `STATUS.md` (T7) for the before/after numbers.

--- Feature #5 (Future-Me Chatbot), T2 ------------------------------

`project_long_term()` extends this module for the chatbot's `1y`/`5y`/
`10y` horizons (`present` needs no extension - it maps 1:1 onto
`forecast(horizon="next_salary")` above, called directly by T7). It
deliberately does NOT reuse `_build_series`'s per-event-date model:
tracking individual projected Topf-1 occurrences (quarterly bills,
annual taxes, ...) one by one over a 10-year/120-occurrence span is both
noisy and pointless at that resolution. Instead every recurring payment
is collapsed into one monthly-equivalent rate (income and fixed expense
separately), and growth/inflation are applied to that rate via monthly
compounding from the annual `salary_growth_pct`/`inflation_pct`
assumptions - see `ASSISTANT_STATUS.md`, T2 for the full reasoning and
the two decisions that were escalated to the team rather than assumed:
fixed costs (Topf 1) stay nominal (do NOT inflate), and the variance
band around the expected line reuses the exact same sqrt-dampening
formula as `_build_series` above, just with the spread itself scaled by
the same inflation factor as the underlying variable spend.
"""

from __future__ import annotations

import calendar
import math
from collections import defaultdict
from datetime import date, timedelta
from typing import Literal, NamedTuple

from app.core.config import (
    DEFAULT_BUFFER_CHF,
    INFLATION_DEFAULT_PCT,
    SALARY_GROWTH_DEFAULT_PCT,
    VARIABLE_BASELINE_MONTHS,
)
from app.models.recurring_payment import AmountHistoryEntry, RecurringPayment
from app.models.transaction import Transaction
from app.repositories.balance_repository import BalanceRepository
from app.repositories.transaction_repository import monthly_category_stats
from app.schemas.forecast import (
    AddRecurring,
    AdjustCategory,
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
DAYS_PER_MONTH = _DAYS_PER_MONTH  # public alias - T5 (Feature #5) needs this too for "present"-horizon month fractions
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
    category_adjustments: list[AdjustCategory] = []


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


def _category_factor(adj: AdjustCategory, matched_median_total: float) -> float:
    """Uniform scale factor an adjustment applies to its matched
    categories' median/P25/P75. `delta_chf` is distributed
    proportionally across the matched sub-categories (it shifts the
    *total*, not each sub individually); a zero-median match makes the
    delta undistributable -> no-op."""
    if adj.percent is not None:
        return max(0.0, 1 + adj.percent / 100)
    if matched_median_total <= 0:
        return 1.0
    return max(0.0, matched_median_total + adj.delta_chf) / matched_median_total


def _matches(adj: AdjustCategory, category_main: str | None, category_sub: str | None) -> bool:
    if adj.category_main != (category_main or ""):
        return False
    return adj.category_sub is None or adj.category_sub == (category_sub or "")


def _variable_monthly_totals(
    classifications: list[Classification],
    as_of: date,
    category_adjustments: list[AdjustCategory] | None = None,
) -> tuple[float, float, float, int]:
    """(monthly_median, monthly_p25, monthly_p75, months_used) - aggregate
    Topf-2 totals per month, summed across categories. Kept at monthly
    granularity (not converted to a daily rate) because the band's
    time-scaling (`_build_series`) needs it in "how many calibrated
    months does this horizon span" terms, not raw days.

    `category_adjustments` (adjust_category scenario) scale the matched
    categories' stats before summing - the band scales along, so a
    halved category also contributes half its spread."""
    variable_txs = [c.transaction for c in classifications if c.topf == "variable"]
    stats = monthly_category_stats(variable_txs, as_of=as_of, months=VARIABLE_BASELINE_MONTHS)
    if not stats:
        return 0.0, 0.0, 0.0, 0

    months_used = stats[0].months_used
    scale: dict[int, float] = {}
    for adj in category_adjustments or []:
        matched = [i for i, s in enumerate(stats) if _matches(adj, s.category_main, s.category_sub)]
        factor = _category_factor(adj, sum(stats[i].median_chf for i in matched))
        for i in matched:
            scale[i] = scale.get(i, 1.0) * factor

    total_median = sum(s.median_chf * scale.get(i, 1.0) for i, s in enumerate(stats))
    total_p25 = sum(s.p25_chf * scale.get(i, 1.0) for i, s in enumerate(stats))
    total_p75 = sum(s.p75_chf * scale.get(i, 1.0) for i, s in enumerate(stats))

    if months_used < 3:
        # Issue edge case: "Unter 3 Monaten: Prognose ohne Band, mit
        # Hinweis" - collapse the band to a line rather than show a
        # meaningless P25/P75 computed from 1-2 data points.
        return total_median, total_median, total_median, months_used

    return total_median, total_p25, total_p75, months_used


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
    variable_schedule: list[tuple[date, float, float, float]],
    resolution_days: int,
    buffer_chf: float,
    salary_day: int | None,
) -> tuple[list[SeriesPoint], TightDate | None]:
    """`variable_schedule`: (start_date, monthly_median, p25, p75)
    segments, sorted, first entry at `as_of`. More than one segment only
    when an `adjust_category` has a future `effective_from` - the
    expected spend accumulates day by day at the active segment's rate,
    so the curve bends on that day. The band uses the active segment's
    spread with the same global sqrt dampening as before - a documented
    simplification (no exact piecewise variance), consistent with the
    band's other approximations."""
    events_by_date: dict[date, float] = defaultdict(float)
    for e in events:
        signed = e.amount_chf if e.flow == "income" else -e.amount_chf
        events_by_date[e.date] += signed

    # Band-width dampening: found via testing that linear growth (rate ×
    # days) makes the band absurdly wide at 365d (~CHF 15'000 span in
    # testing) - it assumes every month re-hits its most extreme P25/P75
    # value independently, i.e. 12 bad months in a row. Real variance
    # partially cancels out over time (the standard deviation of a sum of
    # ~independent months grows with sqrt(months), not with months
    # itself - basic CLT intuition). So only the *expected* spend grows
    # linearly; the spread around it grows with sqrt(months elapsed) -
    # for horizons *beyond* one calibrated month. Below one month, sqrt(x)
    # is actually *larger* than x (e.g. sqrt(0.1) ≈ 0.32), which would
    # make short horizons - including the default "next_salary" view,
    # the app's main headline number - artificially *more* uncertain than
    # before. Found via testing this exact regression before shipping it.
    # `_time_scale` is therefore linear up to 1 month (matches the
    # calibration granularity - there's no sub-month percentile data to
    # justify sqrt behaviour there anyway) and sqrt-dampened beyond it,
    # continuous at the 1-month mark (both pieces equal 1.0 there).
    points: list[SeriesPoint] = []
    tight: TightDate | None = None
    cum_known = 0.0
    var_expected = 0.0
    segment = 0
    d = as_of
    while True:
        cum_known += events_by_date.get(d, 0.0)
        elapsed = (d - as_of).days
        months_elapsed = elapsed / _DAYS_PER_MONTH
        # Accumulated (not `median * months_elapsed`): the daily step is
        # what lets a mid-horizon segment switch bend the curve. For a
        # single segment both forms are numerically equivalent. The
        # increment covers (d-1, d], so it uses the segment active
        # *before* today's switch - on effective_from itself yesterday's
        # rate still applies.
        if elapsed > 0:
            var_expected += variable_schedule[segment][1] / _DAYS_PER_MONTH
        while segment + 1 < len(variable_schedule) and variable_schedule[segment + 1][0] <= d:
            segment += 1
        _, monthly_median, monthly_p25, monthly_p75 = variable_schedule[segment]
        spread_lower = monthly_p75 - monthly_median  # pessimistic gap, per calibrated month
        spread_upper = monthly_median - monthly_p25  # optimistic gap, per calibrated month
        dampened_spread = months_elapsed if months_elapsed <= 1 else math.sqrt(months_elapsed)
        expected = opening_balance + cum_known - var_expected
        lower = opening_balance + cum_known - var_expected - spread_lower * dampened_spread
        upper = opening_balance + cum_known - var_expected + spread_upper * dampened_spread

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

    category_adjustments = _scenario.category_adjustments if _scenario else []
    # Adjustments effective from as_of (or unset) shape the whole curve;
    # each distinct future effective_from adds a segment where it (and
    # everything before it) applies on top.
    active = [
        a for a in category_adjustments if a.effective_from is None or a.effective_from <= as_of
    ]
    pending = sorted(
        (a for a in category_adjustments if a.effective_from and a.effective_from > as_of),
        key=lambda a: a.effective_from,
    )
    monthly_median, monthly_p25, monthly_p75, months_used = _variable_monthly_totals(
        classifications, as_of, active
    )
    variable_schedule = [(as_of, monthly_median, monthly_p25, monthly_p75)]
    for adjustment in pending:
        active.append(adjustment)
        median, p25, p75, _ = _variable_monthly_totals(classifications, as_of, active)
        variable_schedule.append((adjustment.effective_from, median, p25, p75))

    resolution_days = 7 if horizon == "365d" else 1

    series, tight_date = _build_series(
        opening.balance_chf,
        as_of,
        horizon_end,
        events,
        variable_schedule,
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


# --- Feature #5: long-horizon projection (1y/5y/10y) ------------------

LONG_HORIZON_MONTHS: dict[str, int] = {"1y": 12, "5y": 60, "10y": 120}
"""Public so T7 can map `AssistantHorizon` -> `months` for the primary
call. T5 may call `project_long_term` again with a *different* `months`
(e.g. to search further out for `time_to_goal` or `wait_months`) - the
function itself takes a plain month count, not the Literal horizon code,
so it isn't limited to exactly these three spans."""


def _monthly_ratio(annual_pct: float) -> float:
    """Convert an annual growth/inflation percentage into the equivalent
    constant monthly multiplier (`monthly_amount *= ratio` each month) -
    smooth compounding rather than a once-a-year step, so even the `1y`
    horizon (where an annual step might not have "happened" yet depending
    on where `as_of` falls in the year) shows a proportional, continuous
    effect instead of a somewhat arbitrary anniversary date."""
    return (1 + annual_pct / 100) ** (1 / 12)


def _geometric_cum(base_monthly: float, ratio: float, months: int) -> float:
    """sum_{i=0}^{months-1} base_monthly * ratio**i - the closed-form
    total after `months` of compounding, instead of actually looping and
    summing (equivalent, just avoids float drift accumulating over up to
    120 terms and is O(1))."""
    if months <= 0:
        return 0.0
    if abs(ratio - 1.0) < 1e-9:
        return base_monthly * months
    return base_monthly * (ratio**months - 1) / (ratio - 1)


def _monthly_equivalent_total(recurring_payments: list[RecurringPayment], flow: str) -> float:
    """Sum of every *active* RecurringPayment's monthly-equivalent amount
    for one flow direction - the long-horizon model's income/fixed-expense
    base rate. "irregular"-interval payments contribute 0 (not
    projectable, same as `_project_occurrences`/`_known_events` above -
    kept consistent rather than re-deciding this per call site)."""
    return sum(
        rp.amount_chf * _INTERVAL_MONTHLY_FACTOR.get(rp.interval, 0.0)
        for rp in recurring_payments
        if rp.is_active and rp.flow == flow
    )


class LongTermForecast(NamedTuple):
    """Everything T5 (Antwortlogik)/T6 (Chart) need from a long-horizon
    projection. `monthly_*_chf` fields are all "today's CHF" (at `as_of`,
    before growth/inflation) - T5 re-derives any specific month's grown
    value itself via `_monthly_ratio`/`_geometric_cum` if it needs to,
    rather than this type trying to anticipate every downstream need."""

    as_of: date
    horizon_end: date
    opening_balance_chf: float
    series: list[SeriesPoint]
    salary_growth_pct: float
    inflation_pct: float
    savings_rate_pct: float
    monthly_income_chf: float
    monthly_fixed_expense_chf: float
    monthly_variable_expense_chf: float
    monthly_expenses_at_horizon_end_chf: float
    """`monthly_fixed_expense_chf + monthly_variable_expense_chf` grown to
    the *end* of the horizon (fixed stays flat, variable inflates) -
    T5's "wie viele Monatsausgaben" denominator (`buffer_after_months`),
    precomputed here so T5 doesn't need to re-derive `_monthly_ratio`."""
    variable_baseline_months_used: int
    excluded_outliers: list[str]
    notes: list[str]


def project_long_term(
    transactions: list[Transaction],
    recurring_payments: list[RecurringPayment],
    classifications: list[Classification],
    balance_repo: BalanceRepository,
    months: int,
    as_of: date | None = None,
    salary_growth_pct: float | None = None,
    inflation_pct: float | None = None,
    savings_rate_pct: float | None = None,
    category_adjustments: list[AdjustCategory] | None = None,
) -> LongTermForecast:
    """Long-horizon projection for the chatbot's `1y`/`5y`/`10y` (or any
    other month count T5 needs to search) - see module docstring for why
    this doesn't reuse `_build_series`'s per-event-date model. Raises
    `NoBalanceAvailableError` exactly like `forecast()`.
    """
    if months < 1:
        raise ValueError("months must be >= 1")
    if as_of is None:
        as_of = date.today()

    opening = balance_repo.as_of(as_of)
    if opening is None:
        raise NoBalanceAvailableError(as_of)

    g = salary_growth_pct if salary_growth_pct is not None else SALARY_GROWTH_DEFAULT_PCT
    infl = inflation_pct if inflation_pct is not None else INFLATION_DEFAULT_PCT

    base_income = _monthly_equivalent_total(recurring_payments, "income")
    base_fixed = _monthly_equivalent_total(recurring_payments, "expense")
    base_var_median, base_var_p25, base_var_p75, months_used = _variable_monthly_totals(
        classifications, as_of, category_adjustments
    )

    if savings_rate_pct is not None:
        resolved_savings_rate_pct = savings_rate_pct
    elif base_income > 0:
        # "aus der Historie berechnet" (issue) - what fraction of today's
        # recurring income is left over after today's fixed+variable
        # baseline, reported back so the UI can show it as the effective
        # default even when the user never touched the slider.
        resolved_savings_rate_pct = round((base_income - base_fixed - base_var_median) / base_income * 100, 1)
    else:
        resolved_savings_rate_pct = 0.0

    r_income = _monthly_ratio(g)
    r_var = _monthly_ratio(infl)

    spread_lower_base = base_var_p75 - base_var_median  # pessimistic gap, today's CHF
    spread_upper_base = base_var_median - base_var_p25  # optimistic gap, today's CHF

    horizon_end = _step_months(as_of, months)
    series: list[SeriesPoint] = []
    for m in range(0, months + 1):
        d = _step_months(as_of, m)
        cum_income = _geometric_cum(base_income, r_income, m)

        if savings_rate_pct is not None:
            # Override replaces the income-minus-expenses computation for
            # the *expected* line entirely (issue: "überschreibbar") -
            # the band still comes from real variable-spend variance
            # below, the override isn't assumed to change uncertainty.
            cum_net = (savings_rate_pct / 100) * cum_income
        else:
            cum_var = _geometric_cum(base_var_median, r_var, m)
            cum_fixed = base_fixed * m  # flat - fixed costs don't inflate, team decision (T2)
            cum_net = cum_income - cum_fixed - cum_var

        expected = opening.balance_chf + cum_net

        # Same sqrt-dampened-spread formula as `_build_series` above
        # (months_elapsed <= 1: linear; beyond: sqrt) - the spread itself
        # is scaled by the same inflation factor as the variable spend it
        # comes from, so the band's *relative* width relative to expected
        # spend stays consistent across the whole horizon.
        dampened = m if m <= 1 else math.sqrt(m)
        spread_scale = r_var**m
        lower = expected - spread_lower_base * spread_scale * dampened
        upper = expected + spread_upper_base * spread_scale * dampened

        series.append(
            SeriesPoint(
                date=d,
                expected_chf=round(expected, 2),
                lower_chf=round(lower, 2),
                upper_chf=round(upper, 2),
            )
        )

    notes: list[str] = []
    if base_income == 0:
        notes.append("Keine aktive wiederkehrende Einnahme erkannt - Hochrechnung ohne Lohnwachstums-Basis.")
    if 0 < months_used < VARIABLE_BASELINE_MONTHS:
        notes.append(f"Nur {months_used} Monate Historie verfügbar statt {VARIABLE_BASELINE_MONTHS}.")
    if months_used < 3:
        notes.append("Weniger als 3 Monate Historie - Prognose ohne Band (P25 = P75 = Median).")

    return LongTermForecast(
        as_of=as_of,
        horizon_end=horizon_end,
        opening_balance_chf=opening.balance_chf,
        series=series,
        salary_growth_pct=g,
        inflation_pct=infl,
        savings_rate_pct=resolved_savings_rate_pct,
        monthly_income_chf=round(base_income, 2),
        monthly_fixed_expense_chf=round(base_fixed, 2),
        monthly_variable_expense_chf=round(base_var_median, 2),
        monthly_expenses_at_horizon_end_chf=round(base_fixed + base_var_median * (r_var**months), 2),
        variable_baseline_months_used=months_used,
        excluded_outliers=_excluded_outliers(classifications, as_of, VARIABLE_BASELINE_MONTHS),
        notes=notes,
    )


# --- POST /forecast/simulate ------------------------------------------


def apply_adjustments(
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
    category_adjustments: list[AdjustCategory] = []

    for adj in adjustments:
        if isinstance(adj, AdjustCategory):
            # Applied against the variable baseline, not the recurring
            # payments - forecast() picks these up via the overrides.
            category_adjustments.append(adj)

        elif isinstance(adj, CancelRecurring):
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
        recurring_payments=list(result.values()),
        cancel_from=cancel_from,
        one_off_events=one_offs,
        category_adjustments=category_adjustments,
    )


def _monthly_equivalent_impact(
    adjustments: list[Adjustment],
    baseline_recurring: list[RecurringPayment],
    classifications: list[Classification] | None = None,
    as_of: date | None = None,
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

    # Baseline category medians, for adjust_category impacts. Lazy: only
    # computed when such an adjustment is actually present.
    category_stats = None
    if classifications is not None and as_of is not None and any(
        isinstance(a, AdjustCategory) for a in adjustments
    ):
        variable_txs = [c.transaction for c in classifications if c.topf == "variable"]
        category_stats = monthly_category_stats(
            variable_txs, as_of=as_of, months=VARIABLE_BASELINE_MONTHS
        )

    impact = 0.0
    for adj in adjustments:
        if isinstance(adj, AdjustCategory):
            if category_stats is None:
                continue
            matched_total = sum(
                s.median_chf
                for s in category_stats
                if _matches(adj, s.category_main, s.category_sub)
            )
            # Positive = better: a cut (factor < 1) frees up money.
            impact += matched_total * (1 - _category_factor(adj, matched_total))
        elif isinstance(adj, CancelRecurring):
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
    overrides = apply_adjustments(recurring_payments, adjustments)
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
        monthly_chf=_monthly_equivalent_impact(
            adjustments, recurring_payments, classifications, baseline.as_of
        ),
        cumulative_series=diff_points,
        total_at_horizon_chf=total_at_horizon,
        tight_date_shift_days=tight_shift,
    )
    return SimulateResponse(baseline=baseline, scenario=scenario, diff=diff)
