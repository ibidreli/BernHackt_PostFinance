"""Shared merchant normalization helpers.

Centralized so recurring detection, graph aggregation, and any future import
step use identical canonicalization rules.
"""

from __future__ import annotations


def canonical_merchant_key(merchant: str) -> str:
    """First whitespace token of the extracted merchant name."""
    return merchant.split(" ", 1)[0] if merchant else merchant

