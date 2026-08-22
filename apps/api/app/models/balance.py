"""Balance snapshot.

Per the issue's original data model this had `id`/`account_id` as DB
primary/foreign keys - dropped here since there's no database (see
`app/repositories/transaction_repository.py` module docstring) and a
single hardcoded account is in scope (multi-account is explicitly out of
scope in the issue).

In practice a `Balance` is derived straight from a transaction's
`balance_chf` - the CSV export already carries a running balance per
booking (see `app/models/transaction.py`), so nothing needs to be stored
separately. This type exists so `balance_repository.py` (T5/T6) has a
stable return shape, and to cover the "kein Saldo vorhanden" edge case
from the issue, where a user-entered starting balance has no transaction
to attach to.
"""

from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel


class Balance(BaseModel):
    as_of: date
    balance_chf: float
    source: Literal["transaction", "manual"] = "transaction"
    """"transaction": read off a booking's running balance.
    "manual": user-entered starting balance (no transaction history yet -
    see the "Kein Saldo vorhanden" edge case in the issue)."""
