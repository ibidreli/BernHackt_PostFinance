"""Domain model for a single normalized booking.

Pydantic, not an ORM entity - there is no database (see repository docstring
for why). This is the shared unit that recurring-payment detection,
Topf-classification, and the balance/median repositories all build on.
"""

from __future__ import annotations

from datetime import date

from pydantic import BaseModel


class Transaction(BaseModel):
    date: date
    value_date: date
    text: str
    """Raw `Avisierungstext`, kept for debugging/audit and as a fallback
    display value where merchant extraction is weak."""
    merchant: str
    """Best-effort extracted counterparty name. See
    `app/repositories/transaction_repository.py` for how this is derived
    and its known gaps."""
    bank_label: str | None
    """The export's own `Label` column. Observed to always be empty in
    the sample data - kept in case the real export populates it."""
    category_main: str | None
    category_sub: str | None
    amount_chf: float
    """Signed: negative = expense, positive = income."""
    flow: str
    """`"expense"` or `"income"`."""
    balance_chf: float
    """Running account balance after this booking, taken directly from
    the export's `Saldo in CHF` column."""
    is_transfer: bool = False
    """Not detected yet - intentional scope decision, to be calibrated
    against the real dataset. See repository module docstring for
    candidate signals found in the sample data."""
