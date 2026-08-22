"""Pydantic schemas for the forecast API (T8), matching the issue's API
contract shape 1:1 (field names/nesting) with two documented deviations:

- `recurring_id` is a `str` (the RecurringPayment's canonical merchant
  name, see `app/models/recurring_payment.py`), not an `int` DB PK -
  consistent with the "no database" decision throughout this feature.
- `Assumptions` has an extra `notes: list[str]` field beyond the issue's
  example JSON, used for the free-text edge-case hints the issue asks
  for ("Lohntag nicht erkennbar", "weniger als 6 Monate Historie", ...)
  without needing a dedicated boolean per edge case.

Built together with T7 (`app/services/forecast_service.py`), which
returns these directly - there's no separate internal representation to
keep in sync with the API contract.
"""

from __future__ import annotations

from datetime import date
from typing import Annotated, Literal, Union

from pydantic import BaseModel, Field

from app.models.recurring_payment import Interval

Horizon = Literal["next_salary", "30d", "90d", "365d"]


class NextSalary(BaseModel):
    """Next detected salary date, projected forward from the recurring pattern."""

    # NB: `date: date` (field name == type name) can't take a `Field(...)`
    # default directly here - a known pydantic quirk with postponed
    # annotation evaluation (`from __future__ import annotations`): the
    # class's own `date` attribute shadows the `datetime.date` type during
    # forward-ref resolution. Plain annotation, no Field() call.
    date: date
    amount_chf: float = Field(description="Most recent known salary amount (see RecurringPayment.amount_chf).")


class FreeToSpend(BaseModel):
    """The projected balance at `horizon_end` - the "CHF X frei" headline
    number. Equal to the last point of `series`, restated here so the
    frontend doesn't have to reach into the series array for it."""

    expected_chf: float = Field(description="Projected balance using the median variable-spend rate.")
    lower_chf: float = Field(description="Pessimistic projection (P75 variable spend) - the honest worst case.")
    upper_chf: float = Field(description="Optimistic projection (P25 variable spend).")


class TightDate(BaseModel):
    """The day the pessimistic (lower-band) balance first drops below the
    buffer. `null` on the response if the buffer is never breached within
    the horizon - the frontend should then show the series' lowest point
    instead, not treat it as "no data"."""

    date: date
    days_until: int = Field(description="Days from `as_of` until this date.")
    days_before_salary: int | None = Field(
        description="Days between this date and the *next* salary date after it "
        "(not the salary date from `as_of` - see STATUS.md T7 for why that distinction matters)."
    )
    projected_balance_chf: float = Field(description="The pessimistic (lower-band) balance on this date.")


class KnownPayment(BaseModel):
    """One deterministic Topf-1 booking (or simulated one-off/added
    recurring payment) projected into the horizon."""

    date: date
    label: str
    amount_chf: float = Field(
        description="Positive magnitude regardless of expense/income, matching "
        "RecurringPayment.amount_chf's convention."
    )
    category: str | None
    recurring_id: str | None = Field(
        description="Stable id for cancel_recurring/adjust_recurring "
        "(merchant+category+flow, see recurring_payment_id()). "
        "null for one-off adjustments that don't map back to a detected RecurringPayment."
    )


class SeriesPoint(BaseModel):
    date: date
    expected_chf: float
    lower_chf: float
    upper_chf: float


class Assumptions(BaseModel):
    """Makes the forecast checkable - the answer to "where do these
    numbers come from?". Not optional per the issue."""

    variable_baseline_method: str = Field(description='e.g. "median_6m" - how many months the Topf-2 baseline used.')
    band_method: str = Field(description='"p25_p75" normally, "none" if under 3 months of history (band disabled).')
    excluded_outliers: list[str] = Field(
        description="Merchant names excluded from the baseline as Topf-3 outliers, so nobody thinks they were forgotten."
    )
    interest_applied: bool = Field(
        default=False, description="Always false - this is a pure summation, no return/interest assumption."
    )
    salary_day_detected: bool = Field(description="False if the salary day had to fall back to calendar-month behaviour.")
    variable_baseline_months_used: int
    notes: list[str] = Field(
        default_factory=list,
        description="Free-text edge-case hints (e.g. Lohntag nicht erkennbar, kurze Historie) for direct UI display.",
    )


class ForecastResponse(BaseModel):
    as_of: date
    horizon: Horizon
    horizon_end: date
    opening_balance_chf: float
    next_salary: NextSalary | None
    free_to_spend: FreeToSpend
    tight_date: TightDate | None
    known_payments: list[KnownPayment]
    series: list[SeriesPoint] = Field(
        description="Cumulated balance curve, daily resolution (weekly for horizon=365d)."
    )
    assumptions: Assumptions


# --- simulate() request -----------------------------------------------


class CancelRecurring(BaseModel):
    """Preset: "Netflix kündigen". `recurring_id` values come from
    `GET /api/v1/RecurringPayments` (field `recurring_id`, not `merchant` -
    merchant strings aren't unique, see STATUS.md T7)."""

    type: Literal["cancel_recurring"] = "cancel_recurring"
    recurring_id: str
    effective_from: date | None = Field(
        default=None,
        description="Default: cancelled immediately. If set, occurrences before this date "
        'still happen - issue\'s "Gekündigtes Abo, das noch bis Periodenende läuft" edge case.',
    )


class AdjustRecurring(BaseModel):
    """Preset: "Miete +200"."""

    type: Literal["adjust_recurring"] = "adjust_recurring"
    recurring_id: str
    delta_chf: float = Field(description='Added to the current magnitude, e.g. +200 for "Miete +200".')


class AddRecurring(BaseModel):
    """E.g. a new subscription not yet in the transaction history."""

    type: Literal["add_recurring"] = "add_recurring"
    label: str
    amount_chf: float
    interval: Interval
    start_date: date


class OneOff(BaseModel):
    """Single dated event, e.g. "kann ich mir ein Auto für 30'000
    leisten?" (Feature 3 use case, not exposed in this feature's own UI).
    `amount_chf` is always a positive expense magnitude - see
    STATUS.md T7 for the sign-convention bug this was found by testing."""

    type: Literal["one_off"] = "one_off"
    label: str
    amount_chf: float
    date: date


Adjustment = Annotated[
    Union[CancelRecurring, AdjustRecurring, AddRecurring, OneOff],
    Field(discriminator="type"),
]


class SimulateRequest(BaseModel):
    horizon: Horizon = "next_salary"
    as_of: date | None = Field(default=None, description="Fixierbar für Tests/Demo. Default: heute.")
    adjustments: list[Adjustment] = Field(description="One or more adjustments, combinable (see issue's Chips UI).")


class DiffPoint(BaseModel):
    date: date
    diff_chf: float


class Diff(BaseModel):
    """`scenario - baseline`, always "positive = better" (more balance,
    more buffer days) - see STATUS.md T7 for why this doesn't match the
    issue's own (ambiguous) example JSON sign."""

    monthly_chf: float = Field(
        description="Net monthly-equivalent impact of the recurring adjustments alone (excludes one-offs)."
    )
    cumulative_series: list[DiffPoint] = Field(description="scenario.series - baseline.series, point by point.")
    total_at_horizon_chf: float = Field(description="The single headline number: balance difference at horizon_end.")
    tight_date_shift_days: int | None = Field(
        description="Positive = scenario's tight_date is later (more buffer). "
        "null if either baseline or scenario never hits the buffer within the horizon."
    )


class SimulateResponse(BaseModel):
    baseline: ForecastResponse
    scenario: ForecastResponse
    diff: Diff


# --- OData response envelopes (typed purely so Swagger shows the real
# response shape instead of a generic `dict` - see app/api/routes/
# forecast.py, which returns these via `odata_single()`) ------------


class ForecastEnvelope(ForecastResponse):
    """`GET /api/v1/GetForecast` response body."""

    odata_context: str = Field(alias="@odata.context")


class SimulateEnvelope(SimulateResponse):
    """`POST /api/v1/Simulate` response body."""

    odata_context: str = Field(alias="@odata.context")
