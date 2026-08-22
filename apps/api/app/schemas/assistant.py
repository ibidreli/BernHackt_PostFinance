"""Pydantic schemas for the assistant API (Feature 3), matching the
issue's API contract 1:1 with two documented deviations:

- `facts.wait_months` is added (the issue's acceptance criteria demand a
  wait time for `status="tight"` but its example `facts` block omits the
  field).
- `chart.series` points carry an optional `baseline_chf` used only by the
  `before_after` chart type, so all three chart types share one point
  shape instead of needing three.

Note the horizons here are *not* `app.schemas.forecast.Horizon`: the
forecast service tops out at 365d, the assistant projects further (see
`app/services/assistant_service.py` for how it extrapolates the forecast
deterministically rather than re-implementing it).
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

AssistantHorizon = Literal["present", "1y", "5y", "10y"]
Intent = Literal["affordability", "what_if", "time_to_goal"]
Status = Literal["yes", "tight", "no_unless", "needs_clarification", "unsupported"]
ChartType = Literal["wealth_over_time", "goal_progress", "before_after"]


class Assumptions(BaseModel):
    """The three visible sliders. `null` means "use the value derived
    from the history" - only the savings rate has such a derivation."""

    salary_growth_pct: float = Field(default=1.0, ge=0, le=5)
    inflation_pct: float = Field(default=1.5, ge=0, le=5)
    savings_rate_pct: float | None = Field(default=None, ge=0, le=100)


class AskContext(BaseModel):
    conversation_id: str | None = None
    pending_clarification: str | None = Field(
        default=None, description="`clarification.field` of the question being answered by `message`."
    )


class AskRequest(BaseModel):
    message: str
    horizon: AssistantHorizon = "5y"
    assumptions: Assumptions = Assumptions()
    context: AskContext = AskContext()


class Facts(BaseModel):
    target_chf: float
    projected_chf: float
    gap_chf: float = Field(description="target - projected, clamped at 0 once the goal is reached.")
    required_monthly_chf: float = Field(description="gap / months_remaining.")
    months_remaining: int
    buffer_after_months: float = Field(
        description="Remaining balance after the goal, expressed in current monthly expenses."
    )
    wait_months: int | None = Field(
        default=None, description="Only set for status=tight: months until the buffer is back at 3 monthly expenses."
    )


class Lever(BaseModel):
    """One variable category the user could act on. Fixed costs never
    appear here - "spar bei der Krankenkasse" is not advice."""

    category: str
    monthly_avg_chf: float
    potential_chf: float


class ChartPoint(BaseModel):
    date: str = Field(description="YYYY-MM.")
    expected_chf: float
    lower_chf: float
    upper_chf: float
    baseline_chf: float | None = Field(default=None, description="before_after only: the unchanged curve.")


class Chart(BaseModel):
    """Chosen from three fixed types, never generated. The frontend owns
    the rendering; this is data only."""

    type: ChartType
    series: list[ChartPoint]
    target_line_chf: float | None = None
    crossing_date: str | None = Field(default=None, description="YYYY-MM the expected curve first crosses the target.")


class AssumptionsUsed(Assumptions):
    savings_rate_pct: float
    interest_applied: bool = Field(default=False, description="Always false - pure summation, no return assumption.")
    notes: list[str] = Field(default_factory=list, description="Plain-text caveats shown under the answer.")


class Clarification(BaseModel):
    question: str
    options: list[str]
    field: str


class AskResponse(BaseModel):
    intent: Intent | None
    status: Status
    horizon: AssistantHorizon = Field(
        default="5y",
        description="The horizon actually used. A horizon named in the text beats the switcher, "
        "and the frontend moves the switcher to match.",
    )
    answer: str
    facts: Facts | None = None
    levers: list[Lever] = []
    chart: Chart | None = None
    assumptions_used: AssumptionsUsed
    clarification: Clarification | None = None
    source: Literal["live", "cached", "template"] = "template"


class SuggestionsResponse(BaseModel):
    horizon: AssistantHorizon
    suggestions: list[str]
