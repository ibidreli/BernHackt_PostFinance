"""Chart-Auswahl (Feature #5, T6): maps an `AnswerResult` (T5) onto
exactly one of the three fixed chart types from `app/schemas/assistant.py`.

Pure code, no LLM involved - matches the issue's "Das Modell generiert
keine Charts, es wählt nur einen von drei Typen" *literally*: here, the
model doesn't even get to choose the type, the mapping is a fixed
function of `intent` alone, not something inferred per-question. That's
a deliberately stricter reading than "the model picks one of three" -
one intent, one chart type, always - simpler and impossible to get wrong
in a demo.

Mapping (from the issue's table, disambiguated - the table lists
`time_to_goal` under both `wealth_over_time` and `goal_progress`;
`goal_progress` is the more specific chart, built exactly around the
`goal_date`/`goal_date_earliest`/`goal_date_latest` fields T5 already
computes for `time_to_goal`, so that's the one used):

    affordability -> wealth_over_time
    time_to_goal  -> goal_progress
    what_if       -> before_after   (regardless of yes/tight/no_unless)
"""

from __future__ import annotations

from app.schemas.assistant import (
    BeforeAfterChart,
    Chart,
    ChartSeriesPoint,
    GoalProgressChart,
    IntentType,
    WealthOverTimeChart,
)
from app.schemas.forecast import SeriesPoint
from app.services.answer_service import AnswerResult, first_crossing


def _to_chart_points(series: list[SeriesPoint]) -> list[ChartSeriesPoint]:
    """Field-for-field copy from forecast_service's `SeriesPoint` (the
    compute layer) to the assistant schema's `ChartSeriesPoint` (the
    presentation layer) - kept as two distinct types on purpose (see
    ASSISTANT_STATUS.md T1) rather than reusing one class across layers."""
    return [ChartSeriesPoint(date=p.date, expected_chf=p.expected_chf, lower_chf=p.lower_chf, upper_chf=p.upper_chf) for p in series]


def build_affordability_chart(result: AnswerResult) -> WealthOverTimeChart:
    target = result.facts.target_chf
    crossing = first_crossing(result.baseline_series, target, "expected_chf") if target is not None else None
    return WealthOverTimeChart(
        series=_to_chart_points(result.baseline_series),
        target_line_chf=target,
        crossing_date=crossing,
    )


def build_time_to_goal_chart(result: AnswerResult) -> GoalProgressChart:
    assert result.facts.target_chf is not None
    return GoalProgressChart(
        series=_to_chart_points(result.baseline_series),
        target_chf=result.facts.target_chf,
        expected_date=result.facts.goal_date,
        earliest_date=result.facts.goal_date_earliest,
        latest_date=result.facts.goal_date_latest,
    )


def build_what_if_chart(result: AnswerResult) -> BeforeAfterChart:
    assert result.scenario_series is not None, "what_if always sets scenario_series (T5)"
    baseline_points = _to_chart_points(result.baseline_series)
    scenario_points = _to_chart_points(result.scenario_series)
    return BeforeAfterChart(
        baseline_series=baseline_points,
        scenario_series=scenario_points,
        diff_at_horizon_chf=round(scenario_points[-1].expected_chf - baseline_points[-1].expected_chf, 2),
    )


_BUILDERS = {
    "affordability": build_affordability_chart,
    "time_to_goal": build_time_to_goal_chart,
    "what_if": build_what_if_chart,
}


def build_chart(intent: IntentType, result: AnswerResult) -> Chart:
    """T7's single entry point - dispatches on `intent` alone (see module
    docstring for why status doesn't factor in)."""
    builder = _BUILDERS.get(intent)
    if builder is None:  # pragma: no cover - IntentType is exhaustive by construction
        raise ValueError(f"No chart builder for intent {intent!r}")
    return builder(result)
