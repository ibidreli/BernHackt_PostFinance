"""Assistant service (Feature 3): the six-step orchestration from the
issue's architecture diagram.

    Frage -> Extraktion -> Validierung -> forecast_service
          -> Antwortlogik -> Formulierung -> Chart-Auswahl

The load-bearing rule: **no number in the answer is produced by a
language model.** Extraction (`intent_service`) yields parameters only,
the maths runs through `forecast_service.forecast()` - the same function
the Feature 2 slider calls - and the answer text is assembled from
`facts` via templates, so text and facts cannot drift apart
(`_verify_numbers` asserts that at the end).

Beyond 365 days
---------------
`forecast_service` deliberately tops out at a 365d horizon. Rather than
re-implement its logic for 5 and 10 years (which would break the "same
function as the slider" guarantee), the assistant calls it once for 365d
and extrapolates the resulting *rate* forward under the three visible
assumptions:

    balance(m) = opening + SUM(k=1..m) [ net_fixed*(1+g)^(k/12)
                                       - variable*(1+i)^(k/12) ]

where `net_fixed` (income minus fixed costs) and `variable` both come out
of the 365d forecast, `g` is the salary growth slider and `i` the
inflation slider. Band width scales with sqrt(m), the same
variance-of-a-sum argument `forecast_service._build_series` documents -
not linearly, which would imply ten bad years in a row.

Still no interest or return assumption anywhere: `interest_applied` is
false, always. In front of a bank, an unsourced return in a demo is an
own goal.
"""

from __future__ import annotations

import math
import re
from datetime import date
from typing import NamedTuple

from app.repositories.transaction_repository import monthly_category_stats
from app.schemas.assistant import (
    AskRequest,
    AskResponse,
    AssistantHorizon,
    AssumptionsUsed,
    Chart,
    ChartPoint,
    Facts,
    Intent,
    Lever,
)
from app.services import intent_service
from app.services.forecast_service import _variable_monthly_totals, forecast

_HORIZON_MONTHS: dict[AssistantHorizon, int] = {"present": 1, "1y": 12, "5y": 60, "10y": 120}
_INTERVAL_MONTHLY_FACTOR = {"monthly": 1.0, "quarterly": 1 / 3, "yearly": 1 / 12, "irregular": 1.0}

# Issue's threshold for "tight": the goal is reachable but what's left
# afterwards is under three months of expenses. A starting value, to be
# calibrated against the real dataset (issue's "offene Fragen").
TIGHT_BUFFER_MONTHS = 3.0
# Topf 2 contains categories that are variable in the data but not
# actually discretionary (taxes, insurance premiums). Suggesting them as
# a lever is the same mistake as "spar bei der Krankenkasse".
NON_DISCRETIONARY = {"Steuern", "Versicherungen", "Sonstige Geldtransfers"}
# Each lever assumes half the category can be cut. Also a starting value,
# flagged in the issue - the honest alternative is the distance to the
# user's own historical minimum.
LEVER_POTENTIAL_SHARE = 0.5
# Leasing simplification (documented in assumptions_used.notes): 20% down
# payment now, the rest as a monthly rate over the horizon.
LEASING_DOWN_PAYMENT_SHARE = 0.2

_UNSUPPORTED_ANSWER = (
    "Diese Frage kann ich nicht beantworten. Ich kann drei Dinge: "
    "ob eine Anschaffung drinliegt, was eine Änderung deiner Ausgaben bewirkt, "
    "und wann ein Sparziel erreicht ist."
)


class _Basis(NamedTuple):
    """Everything the projection needs, all of it out of the forecast."""

    opening_chf: float
    net_fixed_chf: float
    """Monthly income minus monthly fixed costs - i.e. before variable spend."""
    variable_chf: float
    variable_p25_chf: float
    variable_p75_chf: float
    income_chf: float
    as_of: date
    notes: list[str]

    @property
    def monthly_net_chf(self) -> float:
        return self.net_fixed_chf - self.variable_chf

    @property
    def monthly_expenses_chf(self) -> float:
        return max(self.income_chf - self.monthly_net_chf, 1.0)


# --- step 3: forecast_service ------------------------------------------


def _basis(state, assumptions) -> _Basis:
    """One `forecast()` call, turned into monthly rates. `state` is
    `app.state` (same objects the forecast routes hand over)."""
    result = forecast(
        state.transaction_repository.all(),
        state.recurring_payments,
        state.classifications,
        state.balance_repository,
        horizon="365d",
    )
    variable, p25, p75, _ = _variable_monthly_totals(state.classifications, result.as_of)
    monthly_net = (result.free_to_spend.expected_chf - result.opening_balance_chf) / 12
    income = sum(
        rp.amount_chf * _INTERVAL_MONTHLY_FACTOR[rp.interval]
        for rp in state.recurring_payments
        if rp.flow == "income" and rp.is_active
    )

    notes = list(result.assumptions.notes)
    if monthly_net <= 0:
        notes.append(
            "Deine Ausgaben liegen aktuell über deinen Einnahmen. "
            "Das ist die dringendere Frage als die Zukunftsplanung."
        )

    net_fixed = monthly_net + variable
    if assumptions.savings_rate_pct is not None and income > 0:
        # Slider override: pin the monthly net to the requested share of
        # income and let net_fixed follow, so the override is visible in
        # the curve instead of silently ignored.
        net_fixed = income * assumptions.savings_rate_pct / 100 + variable

    return _Basis(
        opening_chf=result.opening_balance_chf,
        net_fixed_chf=net_fixed,
        variable_chf=variable,
        variable_p25_chf=p25,
        variable_p75_chf=p75,
        income_chf=max(income, 1.0),
        as_of=result.as_of,
        notes=notes,
    )


def _project(basis: _Basis, months: int, growth_pct: float, inflation_pct: float, variable_chf: float | None = None):
    """Cumulated balance per month, expected + band. See module docstring
    for the formula and why the band uses sqrt(m)."""
    # `net_fixed` (income minus fixed costs) is unaffected by a change to
    # variable spend - only the subtracted term moves.
    variable = basis.variable_chf if variable_chf is None else variable_chf
    net_fixed = basis.net_fixed_chf
    g, i = 1 + growth_pct / 100, 1 + inflation_pct / 100

    points, balance = [], basis.opening_chf
    for m in range(1, months + 1):
        balance += net_fixed * g ** (m / 12) - variable * i ** (m / 12)
        spread_down = (basis.variable_p75_chf - basis.variable_chf) * math.sqrt(m)
        spread_up = (basis.variable_chf - basis.variable_p25_chf) * math.sqrt(m)
        month = basis.as_of.month + m
        label = f"{basis.as_of.year + (month - 1) // 12}-{(month - 1) % 12 + 1:02d}"
        points.append((label, balance, balance - spread_down, balance + spread_up))
    return points


def _present_points(state) -> list[tuple[str, float, float, float]]:
    """`present` is the only horizon without assumptions: every figure is
    the forecast's own next-salary-period curve, straight from real data.
    Nothing is extrapolated, so no growth or inflation rate applies -
    which is exactly why it's the right entry point for the demo."""
    result = forecast(
        state.transaction_repository.all(),
        state.recurring_payments,
        state.classifications,
        state.balance_repository,
        horizon="next_salary",
    )
    return [(p.date.isoformat(), p.expected_chf, p.lower_chf, p.upper_chf) for p in result.series]


# --- step 4: Antwortlogik ----------------------------------------------


def _levers(state, as_of: date) -> list[Lever]:
    """The three variable categories with the highest monthly average.
    Topf 1 (fixed) never qualifies - telling someone to save on their
    health insurance is not advice."""
    variable_txs = [c.transaction for c in state.classifications if c.topf == "variable"]
    stats = sorted(monthly_category_stats(variable_txs, as_of=as_of), key=lambda s: -s.median_chf)
    discretionary = [
        s for s in stats if s.median_chf > 0 and s.category_sub not in NON_DISCRETIONARY
    ]
    return [
        Lever(
            category=s.category_sub or s.category_main or "Übrige",
            monthly_avg_chf=round(s.median_chf, 2),
            potential_chf=round(s.median_chf * LEVER_POTENTIAL_SHARE, 2),
        )
        for s in discretionary[:3]
    ]


def _round_chf(value: float, horizon: AssistantHorizon) -> float:
    """Over a year, francs and centimes are false precision - round to
    CHF 100. `facts` carries the rounded value so the answer text (built
    from `facts`) can never disagree with it."""
    return round(value / 100) * 100.0 if horizon in ("5y", "10y") else round(value, 2)


def _decide(target: float, projected: float, months: int, basis: _Basis, horizon: AssistantHorizon):
    gap = max(target - projected, 0.0)
    expenses = basis.monthly_expenses_chf
    buffer_months = (projected - target) / expenses
    wait = None

    if gap > 0:
        status = "no_unless"
    elif buffer_months >= TIGHT_BUFFER_MONTHS:
        status = "yes"
    else:
        status = "tight"
        missing = TIGHT_BUFFER_MONTHS * expenses - (projected - target)
        wait = max(math.ceil(missing / basis.monthly_net_chf), 1) if basis.monthly_net_chf > 0 else None

    facts = Facts(
        target_chf=_round_chf(target, horizon),
        projected_chf=_round_chf(projected, horizon),
        gap_chf=_round_chf(gap, horizon),
        required_monthly_chf=round(gap / months, 2) if months else 0.0,
        months_remaining=months,
        buffer_after_months=round(buffer_months, 1),
        wait_months=wait,
    )
    return status, facts


# --- step 5: Formulierung (templates, so text == facts) ----------------


def _chf(value: float) -> str:
    return f"CHF {value:,.0f}".replace(",", "'")


def _months(count: int) -> str:
    return "einem Monat" if count == 1 else f"{count} Monaten"


def _no_unless_phrase(facts: Facts, levers: list[Lever]) -> str:
    lever = (
        f" Der grösste Hebel wäre {levers[0].category}, da liegst du bei "
        f"{_chf(levers[0].monthly_avg_chf)} pro Monat."
        if levers
        else ""
    )
    return (
        f"Dir fehlen {_chf(facts.gap_chf)}. Bei {_chf(facts.required_monthly_chf)} mehr pro Monat "
        f"schaffst du es.{lever}"
    )


def _phrase(status: str, intent: Intent, facts: Facts, levers: list[Lever], crossing: str | None) -> str:
    if intent == "what_if":
        # facts.target_chf carries the unchanged baseline here, so the
        # difference below is itself derived from two published numbers.
        direction = "mehr" if facts.projected_chf >= facts.target_chf else "weniger"
        return (
            f"Nach {_months(facts.months_remaining)} sind es rund {_chf(facts.projected_chf)} "
            f"statt {_chf(facts.target_chf)} - {_chf(abs(facts.projected_chf - facts.target_chf))} {direction}."
        )
    if intent == "time_to_goal":
        if crossing:
            return (
                f"Erreicht im {crossing}, bei gleichbleibender Sparquote. "
                f"Am Ende des Horizonts sind es rund {_chf(facts.projected_chf)}."
            )
        return (
            f"Im gewählten Horizont wird das Ziel nicht erreicht: es kommen rund "
            f"{_chf(facts.projected_chf)} zusammen. {_no_unless_phrase(facts, levers)}"
        )
    if status == "yes":
        return (
            f"In {_months(facts.months_remaining)} hast du bei gleichbleibender Sparquote rund "
            f"{_chf(facts.projected_chf)}. Die {_chf(facts.target_chf)} liegen drin, "
            f"danach bleiben dir {facts.buffer_after_months} Monatsausgaben Puffer."
        )
    if status == "tight":
        # Beyond a year it stops being a "wait a bit" answer - the number
        # is still named, just not as a recommendation.
        wait = (
            ""
            if not facts.wait_months
            else f" Ich würde {facts.wait_months} Monate warten."
            if facts.wait_months <= 12
            else f" Bis der Puffer wieder bei drei Monatsausgaben liegt, dauert es {facts.wait_months} Monate."
        )
        return (
            f"Es reicht: rund {_chf(facts.projected_chf)} gegen {_chf(facts.target_chf)}. "
            f"Dein Puffer sinkt danach auf {facts.buffer_after_months} Monatsausgaben.{wait}"
        )
    return _no_unless_phrase(facts, levers)


_NUMBER_RE = re.compile(r"CHF ([\d'’]+)")


def _verify_numbers(answer: str, facts: Facts, levers: list[Lever]) -> bool:
    """Issue's most important safeguard: every amount in the text must
    exist in `facts`. Trivially true for the templates above - kept as an
    explicit gate so it still holds the day the phrasing step becomes an
    LLM call."""
    allowed = {round(v) for v in facts.model_dump().values() if isinstance(v, (int, float))}
    allowed |= {round(l.monthly_avg_chf) for l in levers} | {round(l.potential_chf) for l in levers}
    allowed |= {abs(round(facts.projected_chf - facts.target_chf))}
    return all(int(m.replace("'", "").replace("’", "")) in allowed for m in _NUMBER_RE.findall(answer))


# --- step 6: Chart-Auswahl ---------------------------------------------


def _chart(intent: Intent, points, baseline, target: float | None) -> Chart:
    baseline_by_label = {label: b for label, b, _, _ in baseline} if baseline else {}
    series = [
        ChartPoint(
            date=label,
            expected_chf=round(expected, 2),
            lower_chf=round(lower, 2),
            upper_chf=round(upper, 2),
            baseline_chf=round(baseline_by_label[label], 2) if label in baseline_by_label else None,
        )
        for label, expected, lower, upper in points
    ]
    crossing = next((p.date for p in series if target is not None and p.expected_chf >= target), None)
    chart_type = (
        "before_after" if intent == "what_if" else "goal_progress" if intent == "time_to_goal" else "wealth_over_time"
    )
    return Chart(type=chart_type, series=series, target_line_chf=target, crossing_date=crossing)


# --- orchestration -----------------------------------------------------


def ask(state, request: AskRequest) -> AskResponse:
    categories = sorted({c.transaction.category_sub or c.transaction.category_main or "" for c in state.classifications} - {""})
    extraction = intent_service.extract(request.message, categories)
    basis = _basis(state, request.assumptions)
    used = AssumptionsUsed(
        salary_growth_pct=request.assumptions.salary_growth_pct,
        inflation_pct=request.assumptions.inflation_pct,
        savings_rate_pct=round(basis.monthly_net_chf / basis.income_chf * 100, 1),
        notes=basis.notes,
    )

    if extraction.intent is None:
        return AskResponse(
            intent=None,
            status="unsupported",
            horizon=request.horizon,
            answer=_UNSUPPORTED_ANSWER,
            assumptions_used=used,
        )

    clarification = intent_service.validate(extraction, request.context.pending_clarification)
    if clarification is not None:
        return AskResponse(
            intent=extraction.intent,
            status="needs_clarification",
            horizon=request.horizon,
            answer=clarification.question,
            assumptions_used=used,
            clarification=clarification,
        )

    # Issue's edge case: a horizon named in the text beats the switcher,
    # and the switcher visibly follows (the frontend reads it back off
    # `assumptions_used`-adjacent state, see the response's `horizon`).
    horizon = extraction.horizon or request.horizon
    months = _HORIZON_MONTHS[horizon]
    target = extraction.target_chf or 0.0

    levers = _levers(state, basis.as_of)
    variable = basis.variable_chf
    baseline_points = None

    if extraction.intent == "what_if":
        # No goal amount in a what-if question - the baseline itself is
        # the reference the answer compares against.
        baseline_points = _project(basis, months, used.salary_growth_pct, used.inflation_pct)
        target = baseline_points[-1][1]
        category = extraction.category or (levers[0].category if levers else None)
        reduction = extraction.reduction_pct or 50.0
        monthly = next((l.monthly_avg_chf for l in levers if l.category == category), 0.0)
        if not monthly and category:
            monthly = next(
                (
                    st.median_chf
                    for st in monthly_category_stats(
                        [c.transaction for c in state.classifications if c.topf == "variable"], as_of=basis.as_of
                    )
                    if (st.category_sub or st.category_main) == category
                ),
                0.0,
            )
        variable = max(basis.variable_chf - monthly * reduction / 100, 0.0)
        used.notes.append(
            f"{category} um {reduction:.0f} % reduziert"
            + ("" if extraction.category else " (Kategorie nicht erkannt, grösster Posten angenommen)")
            + "."
        )

    if extraction.payment_type == "leasing" and target:
        used.notes.append(
            f"Leasing vereinfacht gerechnet: {LEASING_DOWN_PAYMENT_SHARE:.0%} Anzahlung, "
            "Rest als monatliche Rate über den Horizont."
        )
        variable += target * (1 - LEASING_DOWN_PAYMENT_SHARE) / months
        target *= LEASING_DOWN_PAYMENT_SHARE

    points = (
        _present_points(state)
        if horizon == "present"
        else _project(basis, months, used.salary_growth_pct, used.inflation_pct, variable_chf=variable)
    )
    projected = points[-1][1]
    status, facts = _decide(target, projected, months, basis, horizon)
    if extraction.intent == "what_if":
        status = "yes" if facts.projected_chf >= facts.target_chf else "no_unless"

    if status == "no_unless" and extraction.intent != "what_if" and projected + basis.variable_chf * months < target:
        used.notes.append(
            f"Auch ohne alle variablen Ausgaben fehlen dir {_chf(target - projected - basis.variable_chf * months)}."
        )

    # before_after has no goal, so no target line - the baseline curve is
    # the reference instead.
    target_line = None if extraction.intent == "what_if" else (target or None)
    chart = _chart(extraction.intent, points, baseline_points, target_line)
    answer = _phrase(status, extraction.intent, facts, levers, chart.crossing_date)
    if not _verify_numbers(answer, facts, levers):  # pragma: no cover - templates satisfy this by construction
        answer = f"Prognostiziert: {_chf(facts.projected_chf)}, Ziel: {_chf(facts.target_chf)}."

    return AskResponse(
        intent=extraction.intent,
        status=status,
        horizon=horizon,
        answer=answer,
        facts=facts,
        levers=levers if status in ("no_unless", "tight") else levers[:1],
        chart=chart,
        assumptions_used=used,
        source="template",
    )


SUGGESTIONS: dict[AssistantHorizon, list[str]] = {
    "present": [
        "Kann ich mir diesen Monat noch Schuhe für 200 leisten?",
        "Was wäre, wenn ich Gastronomie halbiere?",
        "Wann habe ich 2'000 zusammen?",
    ],
    "1y": [
        "Kann ich mir nächstes Jahr Ferien für 4'000 leisten?",
        "Was wäre, wenn ich Gastronomie halbiere?",
        "Wann habe ich 10'000 zusammen?",
    ],
    "5y": [
        "Kann ich mir in 5 Jahren ein Auto für 30'000 leisten?",
        "Was wäre, wenn ich 20 % weniger für Gastronomie ausgebe?",
        "Wann habe ich 20'000 zusammen?",
    ],
    "10y": [
        "Kann ich mir in 10 Jahren eine Anzahlung von 100'000 leisten?",
        "Was wäre, wenn ich Gastronomie halbiere?",
        "Wann habe ich 50'000 zusammen?",
    ],
}
