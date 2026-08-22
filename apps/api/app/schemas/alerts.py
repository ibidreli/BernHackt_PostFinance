from __future__ import annotations

import datetime as dt
from typing import Literal

from pydantic import BaseModel, Field

AlertType = Literal["duplicate_charge", "large_payment", "category_spike"]
AlertSeverity = Literal["danger", "warning", "info"]


class Alert(BaseModel):
    """Language-neutral alert entity. The frontend owns wording/rendering."""

    alert_id: str = Field(description='Stable slug, e.g. "dup:2026-03-14:migros:45.90".')
    type: AlertType
    severity: AlertSeverity
    date: dt.date | None = Field(default=None, description="Booking date for transaction-level alerts.")
    month: str | None = Field(default=None, description='YYYY-MM for category_spike alerts.')
    merchant: str | None = None
    category_main: str | None = None
    category_sub: str | None = None
    amount_chf: float = Field(description="Positive magnitude. For spikes this is the monthly category total.")
    baseline_chf: float | None = Field(default=None, description="Category/payment baseline used by the alert.")
    count: int | None = Field(default=None, description="Duplicate group size.")
    booking_text: str | None = Field(default=None, description="Raw Avisierungstext reference where applicable.")


class AlertsEnvelope(BaseModel):
    odata_context: str = Field(alias="@odata.context")
    odata_count: int | None = Field(default=None, alias="@odata.count")
    value: list[Alert]
