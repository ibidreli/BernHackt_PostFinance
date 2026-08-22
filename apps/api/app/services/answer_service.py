"""Antwortlogik (Feature #5, T5): turns a validated `ExtractedIntent`
(T3) into the issue's three-state answer (`yes`/`tight`/`no_unless`)
with the concrete numbers behind it (`AssistantFacts`) and the up-to-3
variable-spending levers - the box right after "Validierung" in the
issue's architecture diagram, right before chart selection (T6).

Computes nothing beyond simple arithmetic on numbers `forecast_service`
(Feature #4 + T2) already produced. The actual forecasting math -
Topf-1/2/3, bands, growth/inflation compounding - lives there; this
module only *interprets* it against a target/adjustment. Matches the
issue's "ein Sprachmodell darf bei Geld nicht rechnen" principle just as
much for this plain-Python module as for the LLM itself: everything here
is deterministic and traceable back to `forecast_service`.

Three entry points, one per supported intent - `answer_affordability`,
`answer_time_to_goal`, `answer_what_if` - all returning an `AnswerResult`
that T6 (chart) and T7 (orchestration) consume directly.
"""

from __future__ import annotations

import math
from datetime import date
from typing import Literal, NamedTuple

from app.core.config import TIGHT_BUFFER_MONTHS, VARIABLE_BASELINE_MONTHS
from app.models.recurring_payment import RecurringPayment
from app.models.transaction import Transaction
from app.repositories.balance_repository import BalanceRepository
from app.repositories.transaction_repository import monthly_category_stats
from app.schemas.assistant import (
    AnswerStatus,
    AssistantAssumptions,
    AssistantFacts,
    AssistantHorizon,
    AssumptionsUsed,
    Lever,
)
from app.schemas.forecast import AddRecurring, Adjustment, AdjustRecurring, CancelRecurring, OneOff, SeriesPoint
from app.services.classification import Classification
from app.services.forecast_service import (
    DAYS_PER_MONTH,
    LONG_HORIZON_MONTHS,
    apply_adjustments,
    forecast,
    project_long_term,
    simulate,
)
from app.services.intent_service import ExtractedIntent
from app.services.recurring_detection import recurring_payment_id

# --- shared result type ---------------------------------------------------


class AnswerResult(NamedTuple):
    status: AnswerStatus
    facts: AssistantFacts
    levers: list[Lever]
    assumptions_used: AssumptionsUsed
    baseline_series: list[SeriesPoint]
    scenario_series: list[SeriesPoint] | None
    """Only set for `what_if` - the baseline is what `affordability`/
    `time_to_goal` chart directly, `what_if` charts baseline vs scenario
    (T6)."""


class UnresolvedAdjustmentError(Exception):
    """Raised when a `what_if` adjustment can't be matched against real
    data - e.g. `merchant_hint` doesn't match any known RecurringPayment
    (the gap T3 flagged and explicitly deferred to T5/T7, see
    ASSISTANT_STATUS.md T3/T5). Callers (T7) should treat this as
    `status="unsupported"`, not crash."""


# --- yes/tight/no_unless core (shared by affordability/time_to_goal/what_if) --


def _evaluate_target(
    target_chf: float,
    projected_chf: float,
    monthly_expenses: float,
    monthly_net_savings: float,
    months_remaining: float,
) -> tuple[AnswerStatus, float | None, float | None, float | None, int | None]:
    """(status, gap_chf, required_monthly_chf, buffer_after_months, wait_months).

    Shared verbatim by `affordability` and `time_to_goal` (the issue's
    yes/tight/no_unless table doesn't distinguish between them - both ask
    "is `target_chf` reachable, and how comfortably"). `answer_what_if`
    reuses it too with `target_chf=0.0` - see its docstring for why that
    framing ("does this leave you financially healthy?") is a coherent
    extension of the same three states rather than a new concept.
    """
    reachable = projected_chf >= target_chf
    if not reachable:
        gap_chf = round(target_chf - projected_chf, 2)
        required_monthly_chf = round(gap_chf / months_remaining, 2) if months_remaining > 0 else None
        return "no_unless", gap_chf, required_monthly_chf, None, None

    remaining_after = projected_chf - target_chf
    if monthly_expenses <= 0:
        # No expense baseline to be "tight" against (e.g. no history at
        # all) - reachable and nothing to run out of, call it a clean yes.
        return "yes", None, None, None, None

    buffer_after_months = round(remaining_after / monthly_expenses, 1)
    if buffer_after_months >= TIGHT_BUFFER_MONTHS:
        return "yes", None, None, buffer_after_months, None

    wait_months = _compute_wait_months(remaining_after, monthly_expenses, monthly_net_savings)
    return "tight", None, None, buffer_after_months, wait_months


def _compute_wait_months(remaining_after: float, monthly_expenses: float, monthly_net_savings: float) -> int | None:
    """Closed-form estimate ("if you keep saving at today's net rate,
    how many more months until the buffer recovers to
    TIGHT_BUFFER_MONTHS") - deliberately not a re-simulation with growth
    over the wait period, that's more precision than a rough "wie lange
    noch warten" answer needs. `None` = "not within a sane timeframe at
    this savings rate" (savings rate <= 0)."""
    target_remaining = TIGHT_BUFFER_MONTHS * monthly_expenses
    shortfall = target_remaining - remaining_after
    if shortfall <= 0:
        return 0
    if monthly_net_savings <= 0:
        return None
    return math.ceil(shortfall / monthly_net_savings)


def _monthly_net_savings(savings_rate_pct: float, monthly_income_chf: float) -> float:
    """Reuses `LongTermForecast.savings_rate_pct` (always resolved,
    whether it came from an explicit override or was computed from
    history - see T2) rather than re-branching on override-vs-computed
    here too."""
    return savings_rate_pct / 100 * monthly_income_chf


def _format_category(main: str | None, sub: str | None) -> str | None:
    if main and sub:
        return f"{main} // {sub}"
    return main or sub


def compute_levers(classifications: list[Classification], as_of: date, top_n: int = 3) -> list[Lever]:
    """Top-N variable (Topf-2 only, issue: "'spar bei der Krankenkasse'
    ist kein Rat") categories by monthly average, `potential_chf` =
    median minus the category's actual historical monthly minimum in the
    same window (your decision over the issue's own "pauschal 50%")."""
    variable_txs = [c.transaction for c in classifications if c.topf == "variable"]
    stats = monthly_category_stats(variable_txs, as_of=as_of, months=VARIABLE_BASELINE_MONTHS)
    ranked = sorted(stats, key=lambda s: s.median_chf, reverse=True)[:top_n]
    return [
        Lever(
            category=_format_category(s.category_main, s.category_sub) or "Unbekannt",
            monthly_avg_chf=s.median_chf,
            potential_chf=max(round(s.median_chf - s.min_chf, 2), 0.0),
        )
        for s in ranked
    ]


def _months_remaining_present(horizon_end: date, as_of: date) -> float:
    return max((horizon_end - as_of).days / DAYS_PER_MONTH, 0.1)


# --- affordability / time_to_goal ------------------------------------


def answer_affordability(
    extracted: ExtractedIntent,
    horizon: AssistantHorizon,
    as_of: date,
    transactions: list[Transaction],
    recurring_payments: list[RecurringPayment],
    classifications: list[Classification],
    balance_repo: BalanceRepository,
    assumptions: AssistantAssumptions | None,
) -> AnswerResult:
    """`extracted.target_chf` must be set - T3's `validate_extraction`
    already guarantees this before an `ExtractedIntent` reaches here."""
    target_chf = extracted.target_chf
    assert target_chf is not None

    if horizon == "present":
        fc = forecast(transactions, recurring_payments, classifications, balance_repo, horizon="next_salary", as_of=as_of)
        projected_chf = fc.free_to_spend.expected_chf
        baseline_series = fc.series
        months_remaining = _months_remaining_present(fc.horizon_end, as_of)
        # "present" hat keine Annahmen (issue) - Wachstum/Inflation explizit
        # auf 0 gezwungen, months=1 nur um an die Monatsraten zu kommen.
        lt = project_long_term(
            transactions, recurring_payments, classifications, balance_repo,
            months=1, as_of=as_of, salary_growth_pct=0.0, inflation_pct=0.0,
        )
        monthly_expenses = lt.monthly_fixed_expense_chf + lt.monthly_variable_expense_chf
        assumptions_used = AssumptionsUsed(salary_growth_pct=0.0, inflation_pct=0.0, savings_rate_pct=lt.savings_rate_pct)
    else:
        months = LONG_HORIZON_MONTHS[horizon]
        lt = project_long_term(
            transactions, recurring_payments, classifications, balance_repo,
            months=months, as_of=as_of,
            salary_growth_pct=assumptions.salary_growth_pct if assumptions else None,
            inflation_pct=assumptions.inflation_pct if assumptions else None,
            savings_rate_pct=assumptions.savings_rate_pct if assumptions else None,
        )
        projected_chf = lt.series[-1].expected_chf
        baseline_series = lt.series
        months_remaining = float(months)
        monthly_expenses = lt.monthly_expenses_at_horizon_end_chf
        assumptions_used = AssumptionsUsed(
            salary_growth_pct=lt.salary_growth_pct, inflation_pct=lt.inflation_pct, savings_rate_pct=lt.savings_rate_pct
        )

    monthly_net_savings = _monthly_net_savings(lt.savings_rate_pct, lt.monthly_income_chf)
    status, gap_chf, required_monthly_chf, buffer_after_months, wait_months = _evaluate_target(
        target_chf, projected_chf, monthly_expenses, monthly_net_savings, months_remaining
    )
    levers = compute_levers(classifications, as_of) if status == "no_unless" else []

    facts = AssistantFacts(
        target_chf=target_chf,
        projected_chf=round(projected_chf, 2),
        gap_chf=gap_chf,
        required_monthly_chf=required_monthly_chf,
        # "present" spans a few days, not a stable number of months -
        # rounding it (e.g. 0.3 -> 0) would misleadingly read as "zero
        # months left". None is more honest; `required_monthly_chf` above
        # already used the precise fractional value for its own math.
        months_remaining=None if horizon == "present" else round(months_remaining),
        buffer_after_months=buffer_after_months,
        wait_months=wait_months,
    )
    return AnswerResult(
        status=status, facts=facts, levers=levers, assumptions_used=assumptions_used,
        baseline_series=baseline_series, scenario_series=None,
    )


def answer_time_to_goal(
    extracted: ExtractedIntent,
    horizon: AssistantHorizon,
    as_of: date,
    transactions: list[Transaction],
    recurring_payments: list[RecurringPayment],
    classifications: list[Classification],
    balance_repo: BalanceRepository,
    assumptions: AssistantAssumptions | None,
) -> AnswerResult:
    """`horizon` is never `"present"` here - T3's `validate_extraction`
    forces a clarification for time_to_goal+present (a "wann"-question
    needs an actual search window)."""
    target_chf = extracted.target_chf
    assert target_chf is not None

    months = LONG_HORIZON_MONTHS[horizon]
    lt = project_long_term(
        transactions, recurring_payments, classifications, balance_repo,
        months=months, as_of=as_of,
        salary_growth_pct=assumptions.salary_growth_pct if assumptions else None,
        inflation_pct=assumptions.inflation_pct if assumptions else None,
        savings_rate_pct=assumptions.savings_rate_pct if assumptions else None,
    )
    projected_chf = lt.series[-1].expected_chf
    monthly_net_savings = _monthly_net_savings(lt.savings_rate_pct, lt.monthly_income_chf)
    status, gap_chf, required_monthly_chf, buffer_after_months, wait_months = _evaluate_target(
        target_chf, projected_chf, lt.monthly_expenses_at_horizon_end_chf, monthly_net_savings, float(months)
    )

    goal_date = _first_crossing(lt.series, target_chf, "expected_chf")
    goal_date_earliest = _first_crossing(lt.series, target_chf, "upper_chf")
    goal_date_latest = _first_crossing(lt.series, target_chf, "lower_chf")

    levers = compute_levers(classifications, as_of) if status == "no_unless" else []

    facts = AssistantFacts(
        target_chf=target_chf,
        projected_chf=round(projected_chf, 2),
        gap_chf=gap_chf,
        required_monthly_chf=required_monthly_chf,
        months_remaining=months,
        buffer_after_months=buffer_after_months,
        wait_months=wait_months,
        goal_date=goal_date,
        goal_date_earliest=goal_date_earliest,
        goal_date_latest=goal_date_latest,
    )
    assumptions_used = AssumptionsUsed(
        salary_growth_pct=lt.salary_growth_pct, inflation_pct=lt.inflation_pct, savings_rate_pct=lt.savings_rate_pct
    )
    return AnswerResult(
        status=status, facts=facts, levers=levers, assumptions_used=assumptions_used,
        baseline_series=lt.series, scenario_series=None,
    )


def _first_crossing(series: list[SeriesPoint], target_chf: float, attr: Literal["expected_chf", "lower_chf", "upper_chf"]) -> date | None:
    for point in series:
        if getattr(point, attr) >= target_chf:
            return point.date
    return None


# --- what_if -----------------------------------------------------------


def resolve_adjustment(
    extracted: ExtractedIntent, recurring_payments: list[RecurringPayment], as_of: date
) -> Adjustment | None:
    """Turns T3's raw `adjustment_kind`/`merchant_hint`/amounts into a
    real Feature-4 `Adjustment` - `None` if `cancel`/`adjust` can't be
    matched against real data (the T3->T5 handoff gap noted in
    ASSISTANT_STATUS.md). Callers must treat `None` as unsupported, not
    crash."""
    kind = extracted.adjustment_kind
    if kind in ("cancel", "adjust"):
        rp = _match_merchant(extracted.merchant_hint, recurring_payments)
        if rp is None:
            return None
        rid = recurring_payment_id(rp)
        if kind == "cancel":
            return CancelRecurring(recurring_id=rid)
        return AdjustRecurring(recurring_id=rid, delta_chf=extracted.delta_chf or 0.0)
    if kind == "add":
        amount = extracted.amount_chf or extracted.delta_chf or 0.0
        # T3 doesn't extract an interval (not covered by the fixed
        # Rückfrage-Set) - "monthly" default, documented simplification.
        return AddRecurring(label=extracted.merchant_hint or "Neue Ausgabe", amount_chf=amount, interval="monthly", start_date=as_of)
    if kind == "one_off":
        amount = extracted.amount_chf or 0.0
        # T3 doesn't extract a date either - "as_of" (now) is the most
        # natural reading of "was wäre, wenn ich einmalig X ausgebe".
        return OneOff(label=extracted.merchant_hint or extracted.target_label or "Einmalige Ausgabe", amount_chf=amount, date=as_of)
    return None


def _match_merchant(hint: str | None, recurring_payments: list[RecurringPayment]) -> RecurringPayment | None:
    if not hint:
        return None
    needle = hint.strip().lower()
    candidates = [rp for rp in recurring_payments if needle in rp.merchant.lower()]
    if not candidates:
        return None
    actives = [rp for rp in candidates if rp.is_active]
    pool = actives or candidates
    # Deterministic tie-break for multiple matches: shortest merchant name
    # (most specific match to a short hint like "Netflix").
    return min(pool, key=lambda rp: len(rp.merchant))


def _shift_series(series: list[SeriesPoint], delta_chf: float) -> list[SeriesPoint]:
    """Applies a constant shift to every point - used for `one_off`
    adjustments in the long-horizon (1y/5y/10y) path, where
    `project_long_term`'s aggregate monthly-rate model has no per-event
    date mechanism to place a single dated expense into (see T2's module
    docstring for why). Since `resolve_adjustment` always defaults a
    `one_off`'s date to `as_of` (T3 doesn't extract one), "shift every
    point by the same amount from day 0" is exactly correct, not an
    approximation - it's a permanent balance reduction starting now."""
    return [
        SeriesPoint(
            date=p.date,
            expected_chf=round(p.expected_chf + delta_chf, 2),
            lower_chf=round(p.lower_chf + delta_chf, 2),
            upper_chf=round(p.upper_chf + delta_chf, 2),
        )
        for p in series
    ]


def answer_what_if(
    extracted: ExtractedIntent,
    horizon: AssistantHorizon,
    as_of: date,
    transactions: list[Transaction],
    recurring_payments: list[RecurringPayment],
    classifications: list[Classification],
    balance_repo: BalanceRepository,
    assumptions: AssistantAssumptions | None,
) -> AnswerResult:
    """Status here answers a slightly different question than for
    affordability/time_to_goal - not "is target_chf reachable" (there's
    no target) but "does this change leave you financially healthy",
    reusing `_evaluate_target` with `target_chf=0.0`: `yes` = scenario
    balance stays comfortably positive, `tight` = positive but thin,
    `no_unless` = scenario balance goes negative (`gap_chf` = how much is
    missing to get back to zero). Same three states, same shared
    function - not a new concept per adjustment type.

    Raises `UnresolvedAdjustmentError` if the adjustment can't be
    resolved against real data - callers (T7) must catch this and treat
    it as `status="unsupported"`.
    """
    adjustment = resolve_adjustment(extracted, recurring_payments, as_of)
    if adjustment is None:
        raise UnresolvedAdjustmentError("Konnte den genannten Posten nicht in den Daten finden.")

    if horizon == "present":
        # Feature #4's real simulate() - exact, event-dated, already
        # handles all 4 adjustment types correctly. Reused as-is rather
        # than re-implemented, consistent with "present hat keine
        # Annahmen, present = die bestehende Funktion".
        sim = simulate(
            transactions, recurring_payments, classifications, balance_repo,
            adjustments=[adjustment], horizon="next_salary", as_of=as_of,
        )
        baseline_series = sim.baseline.series
        scenario_series = sim.scenario.series
        scenario_end = sim.scenario.series[-1].expected_chf
        months_remaining = _months_remaining_present(sim.baseline.horizon_end, as_of)
        impact_monthly_chf = sim.diff.monthly_chf
        impact_cumulative_chf = sim.diff.total_at_horizon_chf
        lt = project_long_term(
            transactions, recurring_payments, classifications, balance_repo,
            months=1, as_of=as_of, salary_growth_pct=0.0, inflation_pct=0.0,
        )
        monthly_expenses = lt.monthly_fixed_expense_chf + lt.monthly_variable_expense_chf
        assumptions_used = AssumptionsUsed(salary_growth_pct=0.0, inflation_pct=0.0, savings_rate_pct=lt.savings_rate_pct)
    else:
        months = LONG_HORIZON_MONTHS[horizon]
        salary_growth_pct = assumptions.salary_growth_pct if assumptions else None
        inflation_pct = assumptions.inflation_pct if assumptions else None
        savings_rate_pct = assumptions.savings_rate_pct if assumptions else None

        lt = project_long_term(
            transactions, recurring_payments, classifications, balance_repo,
            months=months, as_of=as_of,
            salary_growth_pct=salary_growth_pct, inflation_pct=inflation_pct, savings_rate_pct=savings_rate_pct,
        )
        baseline_series = lt.series

        if isinstance(adjustment, OneOff):
            scenario_series = _shift_series(lt.series, -adjustment.amount_chf)
        else:
            overrides = apply_adjustments(recurring_payments, [adjustment])
            scenario_lt = project_long_term(
                transactions, overrides.recurring_payments, classifications, balance_repo,
                months=months, as_of=as_of,
                salary_growth_pct=salary_growth_pct, inflation_pct=inflation_pct, savings_rate_pct=savings_rate_pct,
            )
            scenario_series = scenario_lt.series

        scenario_end = scenario_series[-1].expected_chf
        months_remaining = float(months)
        monthly_expenses = lt.monthly_expenses_at_horizon_end_chf
        impact_cumulative_chf = round(scenario_series[-1].expected_chf - baseline_series[-1].expected_chf, 2)
        impact_monthly_chf = round(impact_cumulative_chf / months, 2)
        assumptions_used = AssumptionsUsed(
            salary_growth_pct=lt.salary_growth_pct, inflation_pct=lt.inflation_pct, savings_rate_pct=lt.savings_rate_pct
        )

    monthly_net_savings = _monthly_net_savings(lt.savings_rate_pct, lt.monthly_income_chf)
    status, gap_chf, required_monthly_chf, buffer_after_months, wait_months = _evaluate_target(
        0.0, scenario_end, monthly_expenses, monthly_net_savings, months_remaining
    )
    levers = compute_levers(classifications, as_of) if status == "no_unless" else []

    facts = AssistantFacts(
        impact_monthly_chf=impact_monthly_chf,
        impact_cumulative_chf=impact_cumulative_chf,
        # "present" spans a few days, not a stable number of months -
        # rounding it (e.g. 0.3 -> 0) would misleadingly read as "zero
        # months left". None is more honest; `required_monthly_chf` above
        # already used the precise fractional value for its own math.
        months_remaining=None if horizon == "present" else round(months_remaining),
        buffer_after_months=buffer_after_months,
        wait_months=wait_months,
        gap_chf=gap_chf,
        required_monthly_chf=required_monthly_chf,
    )
    return AnswerResult(
        status=status, facts=facts, levers=levers, assumptions_used=assumptions_used,
        baseline_series=baseline_series, scenario_series=scenario_series,
    )
