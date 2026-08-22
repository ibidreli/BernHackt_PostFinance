"""Recurring payment: a merchant+category grouping of transactions that
repeat on a detected rhythm. Basis for both the forecast (Topf 1: fixed
costs) and the "Abo-Seite" mentioned in the issue.

Per the issue's original data model this had `id`/`merchant_id`/
`category_id` as DB primary/foreign keys - dropped here since there's no
database (see `app/repositories/transaction_repository.py` module
docstring). `merchant` holds the canonical/grouped merchant name directly
instead of a foreign key into a merchant table.

Detection (interval, day_of_month, is_active, amount_history) is a later
step (T3) - this module only defines the shape. Important input for that
step: merchant names from `extract_merchant()` (T1) are NOT yet
canonicalized - e.g. Netflix appears as "NETFLIX.COM LOS GATOS" /
"NETFLIX.COM AMSTERDAM" / "NETFLIX.COM 866-579-7172" depending on billing
entity/location. Naive exact-match grouping on `Transaction.merchant`
would split one subscription into three separate "recurring payments".
T3 needs to canonicalize merchant names before grouping.
"""

from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel

Interval = Literal["monthly", "quarterly", "yearly", "irregular"]
Flow = Literal["expense", "income"]


class AmountHistoryEntry(BaseModel):
    """One amount change, e.g. Netflix CHF 20.90 -> CHF 21.90."""

    effective_from: date
    amount_chf: float


class RecurringPayment(BaseModel):
    merchant: str
    """Canonical/grouped merchant name (see module docstring)."""
    category_main: str | None
    category_sub: str | None
    amount_chf: float
    """Current/most recent amount."""
    interval: Interval
    day_of_month: int | None
    flow: Flow
    """Salary is recurring too (flow="income")."""
    first_seen: date
    last_seen: date
    is_active: bool
    """False once no matching booking has occurred for 2 intervals."""
    amount_history: list[AmountHistoryEntry] = []
