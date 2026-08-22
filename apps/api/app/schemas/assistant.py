"""Pydantic schemas for the Future-Me Chatbot (Feature #5), T1.

Public REST contract only (`AssistantAskRequest`/`AssistantAskResponse`/
`SuggestionsResponse`) - matches the issue's API contract shape, decided
to follow it literally (REST `/api/v1/assistant/...`, not OData) rather
than fold it into Feature #4's OData subset.

Deliberately does NOT include the LLM-extraction-output schema (the
Structured Output shape for "LLM call #1") - that's built in T3 together
with the actual OpenAI call it belongs to, once the exact fields needed
are known from real prompting, instead of guessing them here up front
("Keep it simple" - don't design a schema twice).

`what_if` is restricted to what Feature #4's four `Adjustment` types
(`app/schemas/forecast.py`) can already express - confirmed with the
team, consistent with Feature #4's own "Kantine halbieren macht keinen
Sinn" decision. Category-percentage questions fall through to
`status="unsupported"`, they don't get a fifth adjustment type.
"""

from __future__ import annotations

from datetime import date
from typing import Annotated, Literal, Union

from pydantic import BaseModel, Field

from app.schemas.forecast import Adjustment

AssistantHorizon = Literal["present", "1y", "5y", "10y"]
"""`present` maps 1:1 onto Feature #4's `horizon=next_salary` (same data,
no assumptions applied - see issue: "Present ist die einzige Stufe ohne
Annahmen"). `1y`/`5y`/`10y` are new long-horizon projections built in T2,
on top of the same Topf-1/2/3 baseline, with salary growth/inflation
applied. Mapping/math lives in `forecast_service`, not here."""

IntentType = Literal["affordability", "what_if", "time_to_goal"]
"""The exactly-three supported question types (issue: "Ein Bot mit drei
Fähigkeiten, die immer funktionieren, ist im Pitch mehr wert...")."""

ResponseIntent = Literal["affordability", "what_if", "time_to_goal", "unsupported"]
"""`IntentType` plus `unsupported` for the top-level response field - a
question outside the three types still needs *some* value here."""

AnswerStatus = Literal["yes", "tight", "no_unless", "needs_clarification", "unsupported"]
"""`yes`/`tight`/`no_unless` are the issue's three-state answer logic
(never a bare yes/no). `needs_clarification` and `unsupported` are the
two special control-flow states - see the request/response docstrings
below for what's populated in each."""

ChartType = Literal["wealth_over_time", "goal_progress", "before_after"]

Source = Literal["live", "cached"]
"""`live`: real OpenAI calls made. `cached`: `ASSISTANT_MODE=cached`, zero
external calls - see T9. Always reflects what actually happened for THIS
request, not the configured `ASSISTANT_MODE` (relevant once a timeout
edge case exists elsewhere - kept as a fact about the response, not the
config)."""


# --- Request --------------------------------------------------------------


class AssistantAssumptions(BaseModel):
    """All three overridable per-request; `None` means "use the default /
    compute from history". Ranges from the issue's own table - validated
    here so an out-of-range slider value 422s instead of silently
    producing a nonsensical multi-decade projection."""

    salary_growth_pct: float | None = Field(default=None, ge=0, le=5, description="Default 1.0 (see core/config.py).")
    inflation_pct: float | None = Field(default=None, ge=0, le=5, description="Default 1.5 (see core/config.py).")
    savings_rate_pct: float | None = Field(
        default=None, ge=0, le=100, description="Default: aus der Transaktionshistorie berechnet, nicht hartkodiert."
    )


class AssistantContext(BaseModel):
    """Carries just enough state for the client to be a source of truth
    too - the server also keeps its own per-`conversation_id` state (T4)
    as the primary mechanism; this is a fallback/override path (e.g.
    after a server restart wipes the in-memory store)."""

    conversation_id: str | None = Field(
        default=None,
        description="Client-generated id used to resolve follow-up questions (T4/T7) against the "
        "previous answer. Without it, every request is handled independently.",
    )
    pending_clarification: str | None = Field(
        default=None,
        description='The `field` value from the previous response\'s `clarification` (e.g. "payment_type") '
        "that this message is answering. Optional - the server-side conversation state (T4) is authoritative "
        "when present.",
    )


class AssistantAskRequest(BaseModel):
    message: str = Field(min_length=1, max_length=1000)
    horizon: AssistantHorizon = Field(
        default="present", description='Umschalter-Wert. Der Text kann das überstimmen (issue: "Der Text gewinnt").'
    )
    assumptions: AssistantAssumptions | None = None
    context: AssistantContext | None = None


# --- Response: facts / levers / clarification -----------------------------


class AssistantFacts(BaseModel):
    """One flexible model instead of a per-intent discriminated union -
    consistent with `Assumptions.notes` in Feature #4's schema (free-text
    extension over rigid per-case modeling). Which fields are populated
    depends on `intent`/`status`; unused ones stay `None`. `null` as a
    whole (not this model) when `status` is `needs_clarification` or
    `unsupported` - there's nothing computed yet in either case.

    Population by intent (set in T5):
    - `affordability`: target_chf, projected_chf, gap_chf (if no_unless),
      required_monthly_chf (if no_unless), months_remaining,
      buffer_after_months (if yes/tight), wait_months (if tight)
    - `time_to_goal`: target_chf, goal_date, goal_date_earliest,
      goal_date_latest, gap_chf (if unreachable within horizon)
    - `what_if`: impact_monthly_chf, impact_cumulative_chf, months_remaining
    """

    target_chf: float | None = None
    projected_chf: float | None = Field(default=None, description="Prognostizierter Betrag am Zieldatum/Horizontende.")
    gap_chf: float | None = Field(default=None, description="target_chf - projected_chf, nur wenn positiv (Fehlbetrag).")
    required_monthly_chf: float | None = Field(default=None, description="gap_chf / verbleibende Monate.")
    months_remaining: int | None = None
    buffer_after_months: float | None = Field(
        default=None, description="Restpuffer am Horizontende, in Monatsausgaben."
    )
    wait_months: int | None = Field(
        default=None, description="Nur bei status=tight: Monate bis der Puffer wieder ≥ TIGHT_BUFFER_MONTHS ist."
    )
    goal_date: date | None = Field(default=None, description="Nur time_to_goal: erwartetes Erreichungsdatum (Median).")
    goal_date_earliest: date | None = Field(default=None, description="Nur time_to_goal: oberes Band (P25 Ausgaben).")
    goal_date_latest: date | None = Field(default=None, description="Nur time_to_goal: unteres Band (P75 Ausgaben).")
    impact_monthly_chf: float | None = Field(
        default=None, description="Nur what_if: monatlich-äquivalente Wirkung der Anpassung, positiv = besser."
    )
    impact_cumulative_chf: float | None = Field(
        default=None, description="Nur what_if: kumulierte Wirkung am Horizontende."
    )


class Lever(BaseModel):
    """One of the top-3 variable (Topf-2 only, issue: "'spar bei der
    Krankenkasse' ist kein Rat") categories by monthly average."""

    category: str
    monthly_avg_chf: float
    potential_chf: float = Field(
        description="monthly_avg_chf minus the category's historical monthly minimum over the baseline "
        "window (decided over the issue's own 'offene Frage #4' - not a flat 50%, see STATUS.md)."
    )


class Clarification(BaseModel):
    question: str
    options: list[str] = Field(description="Button-Optionen, nie eine offene Frage (issue: 'Auf dem Beamer will niemand tippen').")
    field: str = Field(description='Maschinenlesbarer Schlüssel, z.B. "payment_type" - siehe AssistantContext.pending_clarification.')


# --- Response: chart --------------------------------------------------------


class ChartSeriesPoint(BaseModel):
    # NB: field name `date` == type name `date` can't take a `Field(...)`
    # call under `from __future__ import annotations` - same pydantic
    # forward-ref quirk documented in app/schemas/forecast.py::NextSalary.
    date: date
    expected_chf: float
    lower_chf: float
    upper_chf: float


class WealthOverTimeChart(BaseModel):
    """`affordability`, `time_to_goal`: Vermögensverlauf mit Band, Zielbetrag als horizontale Linie."""

    type: Literal["wealth_over_time"] = "wealth_over_time"
    series: list[ChartSeriesPoint]
    target_line_chf: float | None = Field(default=None, description="null bei reinen Prognose-Fragen ohne Zielbetrag.")
    crossing_date: date | None = Field(default=None, description="Erste Kreuzung von expected_chf mit target_line_chf.")


class GoalProgressChart(BaseModel):
    """`time_to_goal`: Fortschritt zum Ziel mit Erreichungs-Korridor."""

    type: Literal["goal_progress"] = "goal_progress"
    series: list[ChartSeriesPoint]
    target_chf: float
    expected_date: date | None = Field(default=None, description="null wenn im Horizont nie erreicht.")
    earliest_date: date | None = Field(default=None, description="Oberes Band (P25 variable Ausgaben).")
    latest_date: date | None = Field(default=None, description="Unteres Band (P75), null wenn im Horizont nie erreicht.")


class BeforeAfterChart(BaseModel):
    """`what_if`, `no_unless`: zwei kumulierte Kurven, Differenz am Horizontende beziffert."""

    type: Literal["before_after"] = "before_after"
    baseline_series: list[ChartSeriesPoint] = Field(description="Ohne Anpassung (gestrichelt im Frontend).")
    scenario_series: list[ChartSeriesPoint] = Field(description="Mit Anpassung.")
    diff_at_horizon_chf: float = Field(
        description="scenario - baseline am Horizontende, positiv = besser - gleiche Konvention wie "
        "Simulate.diff in Feature #4."
    )


Chart = Annotated[
    Union[WealthOverTimeChart, GoalProgressChart, BeforeAfterChart],
    Field(discriminator="type"),
]


# --- Response ---------------------------------------------------------------


class AssumptionsUsed(BaseModel):
    """The resolved (defaults-applied) assumptions actually used for this
    answer - always present except when `status` is `needs_clarification`
    or `unsupported`. Mirrors Feature #4's `Assumptions.interest_applied`
    convention (always false, pure summation, no return assumption)."""

    salary_growth_pct: float = Field(description="0 bei horizon=present (keine Hochrechnung).")
    inflation_pct: float = Field(description="0 bei horizon=present (keine Hochrechnung).")
    savings_rate_pct: float = Field(description="Effektiv verwendete Sparquote, ob Default oder Override.")
    interest_applied: bool = Field(default=False, description="Immer false - reine Summierung, keine Rendite.")


class AssistantAskResponse(BaseModel):
    intent: ResponseIntent
    status: AnswerStatus
    answer: str = Field(description="Bei needs_clarification: die Rückfrage selbst. Bei unsupported: Hinweis auf die 3 Fragetypen.")
    facts: AssistantFacts | None = None
    levers: list[Lever] = Field(default_factory=list)
    chart: Chart | None = None
    assumptions_used: AssumptionsUsed | None = None
    clarification: Clarification | None = None
    source: Source
    intervention: Adjustment | None = Field(
        default=None,
        description='Nur bei what_if: der aufgelöste Eingriff, damit "Als Szenario in Prognose '
        'übernehmen" exakt dasselbe an POST /Simulate übergeben kann.',
    )


# --- GET /suggestions ---------------------------------------------------


class SuggestionsResponse(BaseModel):
    horizon: AssistantHorizon
    suggestions: list[str] = Field(min_length=3, max_length=5, description="3-5 vorformulierte Fragen für Chips.")
