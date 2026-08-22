"""Shared merchant normalization helpers.

Centralized so recurring detection, graph aggregation, and any future import
step use identical canonicalization rules.
"""

from __future__ import annotations

import re

# Card-acquirer branch/terminal codes attached to the chain name, e.g.
# "COOP-1194 BE EIGERPLATZ BERN" -> first token "COOP-1194". Verified
# against the full sample dataset: this "<CHAIN>-<digits>" shape occurs
# 923 times, of which 919 are COOP (49 distinct branch codes) and 4 are
# JUMBO/INTERDISCOUNT - i.e. it's overwhelmingly a Coop-specific export
# quirk, not a general naming convention, so stripping it is safe rather
# than a guess. Without this, Coop alone (18% of all transactions, ~CHF
# 10'265 in the sample) fragments into 51 separate "merchants" - each
# individual branch too thin to read as anything, and none of them
# reading as "Coop" for merchant lookups (graph top-merchants, recurring
# grouping, chatbot merchant_hint matching).
_BRANCH_CODE_RE = re.compile(r"^([A-ZÄÖÜ]+)-\d+$")


def canonical_merchant_key(merchant: str) -> str:
    """First whitespace token of the extracted merchant name, with a
    trailing "-<branch code>" suffix stripped (see `_BRANCH_CODE_RE`)."""
    if not merchant:
        return merchant
    token = merchant.split(" ", 1)[0]
    match = _BRANCH_CODE_RE.match(token)
    return match.group(1) if match else token

