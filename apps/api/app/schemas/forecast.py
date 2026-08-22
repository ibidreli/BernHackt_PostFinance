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
    date: date
    amount_chf: float


class FreeToSpend(BaseModel):
    expected_chf: float
    lower_chf: float
    upper_chf: float


class TightDate(BaseModel):
    date: date
    days_until: int
    days_before_salary: int | None
    projected_balance_chf: float


class KnownPayment(BaseModel):
    date: date
    label: str
    amount_chf: float
    """Positive magnitude regardless of expense/income, matching
    `RecurringPayment.amount_chf`'s convention."""
    category: str | None
    recurring_id: str | None
    """None for one-off adjustments (`simulate`, `type: "one_off"|"add_recurring"`
    before they've been projected) that don't map back to a detected
    RecurringPayment."""


class SeriesPoint(BaseModel):
    date: date
    expected_chf: float
    lower_chf: float
    upper_chf: float


class Assumptions(BaseModel):
    variable_baseline_method: str
    band_method: str
    excluded_outliers: list[str]
    interest_applied: bool = False
    salary_day_detected: bool
    variable_baseline_months_used: int
    notes: list[str] = Field(default_factory=list)


class ForecastResponse(BaseModel):
    as_of: date
    horizon: Horizon
    horizon_end: date
    opening_balance_chf: float
    next_salary: NextSalary | None
    free_to_spend: FreeToSpend
    tight_date: TightDate | None
    known_payments: list[KnownPayment]
    series: list[SeriesPoint]
    assumptions: Assumptions


# --- simulate() request -----------------------------------------------


class CancelRecurring(BaseModel):
    type: Literal["cancel_recurring"] = "cancel_recurring"
    recurring_id: str
    effective_from: date | None = None
    """Default: cancelled immediately. If set, occurrences before this
    date still happen - issue's "Gekündigtes Abo, das noch bis
    Periodenende läuft" edge case."""


class AdjustRecurring(BaseModel):
    type: Literal["adjust_recurring"] = "adjust_recurring"
    recurring_id: str
    delta_chf: float
    """Added to the current magnitude, e.g. +200 for "Miete +200"."""


class AddRecurring(BaseModel):
    type: Literal["add_recurring"] = "add_recurring"
    label: str
    amount_chf: float
    interval: Interval
    start_date: date


class OneOff(BaseModel):
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
    as_of: date | None = None
    adjustments: list[Adjustment]


class DiffPoint(BaseModel):
    date: date
    diff_chf: float


class Diff(BaseModel):
    monthly_chf: float
    cumulative_series: list[DiffPoint]
    total_at_horizon_chf: float
    tight_date_shift_days: int | None
    """Positive = scenario's tight_date is later (more buffer). `None` if
    either baseline or scenario never hits the buffer within the horizon."""


class SimulateResponse(BaseModel):
    baseline: ForecastResponse
    scenario: ForecastResponse
    diff: Diff
