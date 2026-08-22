"""Offline-Fallback (Feature #5, T9): `ASSISTANT_MODE=cached` matches an
incoming message against a small fixed set of prepared demo questions -
no LLM call #1 (extraction) at all. Matched via exact, normalized text
comparison, not fuzzy similarity: this is a controlled-demo fallback
("WLAN streikt in der Halle"), not a general offline NLU - honest about
what it actually does rather than pretending to handle arbitrary
paraphrasing without a working LLM connection.

`forecast_service` still computes real numbers on top of the matched
`ExtractedIntent` either way (via the normal T5/T6 path in
`assistant_service.ask()`) - only the two LLM calls are replaced, not
the computation. The `ExtractedIntent` values below were captured from
real `extract_intent()` runs against these exact questions (see
ASSISTANT_STATUS.md T9) and hand-verified, not invented.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from app.services.intent_service import ExtractedIntent


@dataclass(frozen=True)
class CachedQuestion:
    text: str
    """Canonical question text - also what `GET /suggestions` (T11) can
    surface as a chip so a demo operator can hit it exactly."""
    extracted: ExtractedIntent


CACHED_QUESTIONS: list[CachedQuestion] = [
    CachedQuestion(
        text="Kann ich mir in 5 Jahren ein Auto für 30000 leisten?",
        extracted=ExtractedIntent(
            intent="affordability", horizon_override="5y", target_chf=30000.0, target_label="Auto"
        ),
        # Deliberately triggers the payment_type Rückfrage (target_chf >=
        # LARGE_PURCHASE_THRESHOLD_CHF) - demonstrates that the
        # clarification flow works fully offline too (resolve/apply need
        # no LLM, see T4).
    ),
    CachedQuestion(
        text="Was wäre, wenn ich Netflix kündige?",
        extracted=ExtractedIntent(intent="what_if", adjustment_kind="cancel", merchant_hint="netflix"),
    ),
    CachedQuestion(
        text="Wann habe ich 20000 zusammen?",
        extracted=ExtractedIntent(intent="time_to_goal", target_chf=20000.0),
        # No horizon_override (realistic - the text doesn't name one) -
        # triggers the "Wann ungefähr?" Rückfrage on `present`, same as
        # the live LLM would.
    ),
    CachedQuestion(
        text="Kann ich mir jetzt Kopfhörer für 300 leisten?",
        extracted=ExtractedIntent(
            intent="affordability", horizon_override="present", target_chf=300.0, target_label="Kopfhörer"
        ),
        # Under LARGE_PURCHASE_THRESHOLD_CHF - answers directly, no Rückfrage.
    ),
    CachedQuestion(
        text="Was wäre, wenn ich monatlich 50 mehr für Fitness ausgebe?",
        extracted=ExtractedIntent(
            intent="what_if", adjustment_kind="add", merchant_hint="Fitness", amount_chf=50.0
        ),
    ),
    CachedQuestion(
        text="Was wäre, wenn ich Gastronomie halbiere?",
        extracted=ExtractedIntent(
            intent="what_if", category_percent_hint=True, category_hint="Gastronomie", percent=-50.0
        ),
        # The Sollstatus's adjust_category demo case - proves the category
        # what-if path works fully offline too.
    ),
]

_WHITESPACE_RE = re.compile(r"\s+")
_TRAILING_PUNCTUATION_RE = re.compile(r"[?!.]+$")


def _normalize(text: str) -> str:
    stripped = _TRAILING_PUNCTUATION_RE.sub("", text.strip().lower())
    return _WHITESPACE_RE.sub(" ", stripped)


_BY_NORMALIZED_TEXT = {_normalize(q.text): q for q in CACHED_QUESTIONS}


def match_cached_question(message: str) -> CachedQuestion | None:
    """`None` if `message` isn't one of the prepared demo questions -
    callers (T7) should treat that as `unsupported`, listing the
    available demo questions rather than guessing."""
    return _BY_NORMALIZED_TEXT.get(_normalize(message))
