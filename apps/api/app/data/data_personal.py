"""Raw loader for the `data_personal.csv` bank export.

This is the single place that knows the export's on-disk shape (delimiter,
encoding, column names, date/number formats). It only normalizes column
names and types 1:1 - it does not derive amount/flow/merchant/category
splits or anything domain-specific. That belongs to
`app/repositories/transaction_repository.py` (Feature: Zukunftsprognose),
so other consumers of the raw export can build on this without depending
on forecast-specific logic.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from app.core.config import CSV_DELIMITER, CSV_ENCODING, CSV_PATH

# Export column name -> normalized snake_case name.
_COLUMN_MAP = {
    "Datum": "date",
    "Avisierungstext": "text",
    "Gutschrift in CHF": "credit_chf",
    "Lastschrift in CHF": "debit_chf",
    "Label": "label",
    "Kategorie": "category_raw",
    "Valuta": "value_date",
    "Saldo in CHF": "balance_chf",
}


def load_raw_transactions(path: Path = CSV_PATH) -> pd.DataFrame:
    """Load the bank export CSV as-is, with normalized column names/types.

    Columns after loading:
        date, value_date: pandas Timestamp
        text, label, category_raw: str (label may be NaN - it's often empty)
        credit_chf, debit_chf, balance_chf: float (credit/debit NaN when unset)

    Rows are returned in file order. The export is observed to list the
    newest booking first - callers that need chronological order should
    sort by `date` explicitly rather than relying on this.

    NOT deduplicated: the raw export has 32 groups of byte-identical rows
    (same date, text, amount, category, empty balance). Tried dropping
    them and verified against the running-balance reconstruction (see
    `app/repositories/balance_repository.py`) - for some groups (e.g. a
    triple-listed SBB payment) dropping the extras fixes the balance
    math, but for at least one (two identical "OXYMORON BAAR" TWINT
    purchases on 2023-01-01) the balance math proves *both* are real,
    independent purchases. No column distinguishes the two cases, so
    blanket deduplication is unsafe and was reverted - see
    `app/repositories/balance_repository.py` module docstring for the
    resulting known limitation.
    """
    df = pd.read_csv(path, sep=CSV_DELIMITER, encoding=CSV_ENCODING, dtype=str)
    df = df.rename(columns=_COLUMN_MAP)

    df["date"] = pd.to_datetime(df["date"], format="%d.%m.%Y")
    df["value_date"] = pd.to_datetime(df["value_date"], format="%d.%m.%Y")

    for col in ("credit_chf", "debit_chf", "balance_chf"):
        df[col] = pd.to_numeric(df[col].str.replace(",", ".", regex=False), errors="coerce")

    return df
