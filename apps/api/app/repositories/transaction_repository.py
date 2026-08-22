"""Domain-level transaction normalization and read access.

Turns the raw bank-export DataFrame (`app/data/data_personal.py`) into a
list of `Transaction` domain objects: derives a signed amount + flow from
the separate credit/debit columns, splits the two-level category, and
extracts a best-effort merchant/counterparty name from the free-text
`Avisierungstext` field.

Merchant extraction is regex-based against the templates actually observed
in `data_personal.csv` (verified against all 5303 sample rows):

    KAUF/DIENSTLEISTUNG, KAUF/ONLINE-SHOPPING, APPLE PAY ... KARTEN NR. XXXX####  -> after "KARTEN NR. XXXX####"
    TWINT / GELD SENDEN|EMPFANGEN ... TELEFON-NR. +41...                          -> after the (last) phone number
    LASTSCHRIFT [DAUERAUFTRAG: <ref>] <IBAN> <merchant> <address>                 -> after the IBAN
    GUTSCHRIFT ... AUFTRAGGEBER: / ABSENDER: / ZAHLUNGSEMPFÄNGER: <name>          -> after the keyword
    PREIS FÜR <label> <mm.yyyy>                                                  -> the label

About 9-10% of rows don't match any of these (mostly TWINT purchases with
no card/phone token at all) and fall back to stripping the leading
"<verb> VOM <date>" prefix plus trailing noise - this fallback alone
handles the bulk of that bucket well. A small remainder (~15 rows, mostly
LASTSCHRIFT where an intermediary bank's name precedes the IBAN, e.g. UBS/
Raiffeisen mandates) isn't cleanly split from the actual payee. Documented
here rather than fixed - not worth the engineering time for ~0.3% of rows
in a hackathon timeline.

is_transfer detection is intentionally NOT implemented yet (product
decision: calibrate against the real dataset rather than guess). Candidate
signals found in the sample data: category "Finanzen // Sonstige
Geldtransfers" (314 rows), "Überträge" (14 rows). "Rückerstattungen" (23
rows) are refunds, not transfers - per the issue those need separate
handling ("nicht als Einnahme prognostizieren") in the Topf-3
classification step, not here.

Also holds `monthly_category_stats` (T5): P25/Median/P75 of monthly
category totals, the statistical basis for the Topf-2 band.
"""

from __future__ import annotations

import re
from collections import defaultdict
from datetime import date
from typing import NamedTuple

import pandas as pd

from app.models.transaction import Transaction

# --- merchant extraction ---------------------------------------------------


def _last_match(pattern: re.Pattern[str], text: str) -> re.Match[str] | None:
    """re.search always finds the leftmost match; some templates (e.g.
    "GELD SENDEN ... VON TELEFON-NR. X AN TELEFON-NR. Y , NAME") repeat the
    anchor token, and we want the text after the *last* one."""
    matches = list(pattern.finditer(text))
    return matches[-1] if matches else None


# "GELD SENDEN" carries *two* "TELEFON-NR." tokens (sender AN recipient):
# "... VON TELEFON-NR. X AN TELEFON-NR. Y , NAME". A single-occurrence
# pattern would capture everything after the *first* one, including the
# second "AN TELEFON-NR. Y" literally. `(?:TELEFON-NR\....(?:AN\s+)?)+`
# consumes every such token before capturing the name that follows the
# last one - works whether there's one phone number or two.
_TELEFON_RE = re.compile(r"(?:TELEFON-NR\.\s*\+?\d+\s*(?:AN\s+)?)+(?P<rest>.+)$")
_CARD_RE = re.compile(r"KARTEN NR\.\s*XXXX\d+\s+(?P<rest>.+)$")
_LASTSCHRIFT_IBAN_RE = re.compile(
    r"^LASTSCHRIFT\s+(?:DAUERAUFTRAG:\s*[\w.-]+\s+)?"
    r"[A-Z]{2}\d{2}[\dA-Z]+\s+(?P<rest>.+)$"
)
_AUFTRAGGEBER_RE = re.compile(r"AUFTRAGGEBER:\s*(?P<rest>.+)$")
_ABSENDER_RE = re.compile(r"ABSENDER:\s*(?P<rest>.+)$")
_ZAHLUNGSEMPFAENGER_RE = re.compile(r"ZAHLUNGSEMPF[ÄA]NGER:\s*(?!DES)(?P<rest>.+)$")
_PREIS_RE = re.compile(r"^PREIS F[ÜU]R\s+(?P<rest>.+?)\s+\d{2}\.\d{4}\s*$")

# Fallback: strip everything up to and including "<...> VOM <dd.mm.yyyy> ".
# Non-greedy so it stops at the *first* "VOM <date>", not a later one.
_LEADING_VOM_RE = re.compile(r"^.+?\bVOM\s+\d{2}\.\d{2}\.\d{4}\s+")

_TRAILING_NOTE_RE = re.compile(
    r"\s+(?:MITTEILUNGEN?|REFERENZEN?|REFERENZ-NR|REFERENZ|SENDER REFERENZ):.*$",
    re.IGNORECASE,
)
_TRAILING_WAREN_RE = re.compile(r"\s+WAREN\s+[\d.,]+\s*$")
_TRAILING_COUNTRY_RE = re.compile(r"\s+\([A-Z]{2}\)\s*$")
# Cuts a trailing Swiss-style "<postal code> <city>" address tail, e.g.
# "SWISSCOM (SCHWEIZ) AG 3050 BERN" -> "SWISSCOM (SCHWEIZ) AG".
_POSTAL_CODE_CUT_RE = re.compile(r"\s\d{4}\s.*$")
_MULTI_SPACE_RE = re.compile(r"\s+")


def _clean(candidate: str) -> str:
    c = candidate
    c = _TRAILING_NOTE_RE.sub("", c)
    c = _TRAILING_WAREN_RE.sub("", c)
    c = _TRAILING_COUNTRY_RE.sub("", c)
    c = _POSTAL_CODE_CUT_RE.sub("", c)
    c = c.strip(" ,:-")
    c = _MULTI_SPACE_RE.sub(" ", c)
    return c.strip()


def extract_merchant(text: str) -> str:
    """Best-effort merchant/counterparty name from `Avisierungstext`.

    See module docstring for the fallback rate and known gaps.
    """
    match = (
        _TELEFON_RE.search(text)
        or _last_match(_CARD_RE, text)
        or _LASTSCHRIFT_IBAN_RE.search(text)
        or _AUFTRAGGEBER_RE.search(text)
        or _ABSENDER_RE.search(text)
        or _ZAHLUNGSEMPFAENGER_RE.search(text)
        or _PREIS_RE.search(text)
    )
    if match:
        return _clean(match.group("rest"))

    stripped = _LEADING_VOM_RE.sub("", text, count=1)
    return _clean(stripped)


# --- category split ---------------------------------------------------------


def _split_category(category_raw: str | None) -> tuple[str | None, str | None]:
    """"Einkaufen // Supermärkte" -> ("Einkaufen", "Supermärkte").
    ~0.06% of rows have no "//" (single-level category) or are empty."""
    category_raw = (category_raw or "").strip()
    if not category_raw:
        return None, None
    if "//" in category_raw:
        main, sub = category_raw.split("//", 1)
        return main.strip(), sub.strip()
    return category_raw, None


# --- normalization -----------------------------------------------------


def normalize_transactions(raw: pd.DataFrame) -> list[Transaction]:
    """Turn the raw export DataFrame into normalized, chronologically
    sorted `Transaction`s. Exactly one of credit_chf/debit_chf is set per
    row in the observed export (verified: 0/5303 rows violate this) -
    rows that somehow violate it are skipped rather than crashing the
    whole load.
    """
    transactions: list[Transaction] = []
    for row in raw.itertuples(index=False):
        has_credit = pd.notna(row.credit_chf)
        has_debit = pd.notna(row.debit_chf)
        if has_credit == has_debit:  # neither or both set - malformed row
            continue

        amount = row.credit_chf if has_credit else row.debit_chf
        category_raw = row.category_raw if pd.notna(row.category_raw) else None
        category_main, category_sub = _split_category(category_raw)

        transactions.append(
            Transaction(
                date=row.date.date(),
                value_date=row.value_date.date(),
                text=row.text,
                merchant=extract_merchant(row.text),
                bank_label=row.label if pd.notna(row.label) else None,
                category_main=category_main,
                category_sub=category_sub,
                amount_chf=float(amount),
                flow="income" if has_credit else "expense",
                balance_chf=float(row.balance_chf),
            )
        )

    # The export lists newest-first, including same-day bookings (verified:
    # for two same-day GELD SENDEN bookings, the *earlier* one is the one
    # further down in the file). Reversing first makes the stable sort
    # below resolve same-day ties oldest-first instead of newest-first.
    # Sort key is (date, value_date) for a best-effort sub-day order -
    # value_date is not fully reliable for this (it can predate `date` for
    # card transactions, confirmed against real rows), so the *exact*
    # order of same-day transactions relative to each other isn't always
    # right. Doesn't matter in practice: nothing downstream needs sub-day
    # precision (T3/T4/T5 work at day/month granularity, and
    # `balance_repository.py`'s day-level reconstruction is verified
    # exact regardless - see its module docstring).
    transactions.reverse()
    transactions.sort(key=lambda t: (t.date, t.value_date))
    return transactions


# --- repository --------------------------------------------------------


class TransactionRepository:
    """In-memory read access over normalized transactions.

    No DB: built once from the CSV export at app startup (see
    `app/main.py`) and held in `app.state`.
    """

    def __init__(self, transactions: list[Transaction]):
        self._transactions = transactions

    @classmethod
    def from_raw(cls, raw: pd.DataFrame) -> "TransactionRepository":
        return cls(normalize_transactions(raw))

    def all(self) -> list[Transaction]:
        return list(self._transactions)

    def expenses(self) -> list[Transaction]:
        return [t for t in self._transactions if t.flow == "expense" and not t.is_transfer]

    def incomes(self) -> list[Transaction]:
        return [t for t in self._transactions if t.flow == "income" and not t.is_transfer]


# --- median/percentile per category (T5) --------------------------------

CategoryKey = tuple[str | None, str | None]  # (category_main, category_sub)


class CategoryStats(NamedTuple):
    """P25/Median/P75 of a category's *monthly totals* over the last N
    full calendar months - the basis for the Topf-2 band (see
    `app/services/forecast_service.py`, T7)."""

    category_main: str | None
    category_sub: str | None
    p25_chf: float
    median_chf: float
    p75_chf: float
    months_used: int
    """How many full calendar months actually went into the calculation
    (<= the requested `months`) - drives the "weniger als 6 Monate
    Historie" note in `assumptions` (T7/T8): under 3, the caller should
    disable the band entirely per the issue's edge-case table."""


def _percentile(sorted_values: list[float], p: float) -> float:
    """Linear interpolation between ranks (numpy's default method) -
    deliberately simple rather than pulling in a stats library for this."""
    if not sorted_values:
        return 0.0
    if len(sorted_values) == 1:
        return sorted_values[0]
    idx = p * (len(sorted_values) - 1)
    lower = int(idx)
    upper = min(lower + 1, len(sorted_values) - 1)
    frac = idx - lower
    return sorted_values[lower] + (sorted_values[upper] - sorted_values[lower]) * frac


def _last_full_months(
    as_of: date, max_months: int, earliest: date
) -> list[tuple[int, int]]:
    """Up to `max_months` full calendar months strictly before `as_of`'s
    month, oldest first. The *current* (possibly partial) month is
    deliberately excluded - otherwise an in-progress month would drag the
    median down just for not being over yet. Stops early if `earliest`
    (the first date with any data) doesn't go back far enough, instead of
    inventing history that isn't there.
    """
    keys: list[tuple[int, int]] = []
    year, month = as_of.year, as_of.month
    earliest_key = (earliest.year, earliest.month)
    for _ in range(max_months):
        month -= 1
        if month == 0:
            month, year = 12, year - 1
        if (year, month) < earliest_key:
            break
        keys.append((year, month))
    keys.reverse()
    return keys


def monthly_category_stats(
    transactions: list[Transaction],
    as_of: date,
    months: int = 6,
) -> list[CategoryStats]:
    """P25/Median/P75 of monthly category totals over the last `months`
    full calendar months before `as_of`.

    Expects already-filtered transactions - typically the Topf-2
    ("variable") subset from `app/services/classification.py` (T4), not
    the full transaction list. This function itself is topf-agnostic: it
    just aggregates whatever it's given.

    A category with no booking in a given month still contributes a CHF 0
    data point for that month - otherwise a category only used in 2 of 6
    months would look artificially expensive instead of "used rarely".
    """
    if not transactions:
        return []

    earliest = min(t.date for t in transactions)
    month_keys = _last_full_months(as_of, months, earliest)
    if not month_keys:
        return []
    month_key_set = set(month_keys)

    totals: dict[CategoryKey, dict[tuple[int, int], float]] = defaultdict(dict)
    for t in transactions:
        month_key = (t.date.year, t.date.month)
        if month_key not in month_key_set:
            continue
        by_month = totals[(t.category_main, t.category_sub)]
        by_month[month_key] = by_month.get(month_key, 0.0) + abs(t.amount_chf)

    stats: list[CategoryStats] = []
    for (category_main, category_sub), by_month in totals.items():
        values = sorted(by_month.get(mk, 0.0) for mk in month_keys)
        stats.append(
            CategoryStats(
                category_main=category_main,
                category_sub=category_sub,
                p25_chf=round(_percentile(values, 0.25), 2),
                median_chf=round(_percentile(values, 0.5), 2),
                p75_chf=round(_percentile(values, 0.75), 2),
                months_used=len(month_keys),
            )
        )
    return stats
