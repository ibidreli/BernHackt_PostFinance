"""Domain model for a single normalized booking.

Pydantic, not an ORM entity - there is no database (see repository docstring
for why). This is the shared unit that recurring-payment detection,
Topf-classification, and the balance/median repositories all build on.
"""

from __future__ import annotations

from datetime import date

from pydantic import BaseModel


class Transaction(BaseModel):
    id: str
    date: date
    value_date: date
    text: str
    """Raw `Avisierungstext`, kept for debugging/audit and as a fallback
    display value where merchant extraction is weak."""
    merchant: str
    """Best-effort extracted counterparty name. See
    `app/repositories/transaction_repository.py` for how this is derived
    and its known gaps."""
    merchant_canonical: str
    """Normalized merchant key reused across graph + recurring grouping."""
    bank_label: str | None
    """The export's own `Label` column. Observed to always be empty in
    the sample data - kept in case the real export populates it."""
    category_main: str | None
    category_sub: str | None
    amount_chf: float
    """Signed: negative = expense, positive = income."""
    flow: str
    """`"expense"` or `"income"`."""
    original_amount: float | None = None
    """Original amount in original currency when available (else `None`)."""
    original_currency: str | None = None
    """Original currency (e.g. EUR) when available (else `None`)."""
    status: str | None = None
    """Optional transaction status when available from source data."""
    balance_chf: float
    """Running account balance after this booking, taken directly from
    the export's `Saldo in CHF` column."""
    is_transfer: bool = False
    """Best-effort transfer flag derived from category heuristics."""
