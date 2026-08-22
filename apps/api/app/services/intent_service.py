"""Step 1 of the assistant pipeline: turn a free-text question into
structured parameters, then validate them.

The extraction is deliberately rule-based rather than an LLM call. The
architecture principle of the feature is that the model understands the
question and phrases the answer while *nothing* it produces is a number
used in the maths - a regex satisfies exactly that contract, needs no
API key, and can't time out during the live demo. `prompts/
assistant_extraction.md` documents the equivalent LLM contract; swapping
this module for a model call means returning the same `Extraction`.

Validation is separate from extraction on purpose (issue's "LLM liefert
ungültige Parameter" edge case): implausible or missing parameters lead
to a clarification, never to a calculation with garbage values.
"""

from __future__ import annotations

import re
from typing import NamedTuple

from app.schemas.assistant import AssistantHorizon, Clarification, Intent

# Swiss thousands separators: 30'000 / 30’000 / 30 000 / 30.000 / 30000.
_AMOUNT_RE = re.compile(r"(?<![\d.,'’])(\d{1,3}(?:[\s.'’]\d{3})+|\d+(?:[.,]\d{1,2})?)(?!\d)")
_HORIZON_RES: list[tuple[re.Pattern[str], AssistantHorizon]] = [
    (re.compile(r"\b(10|zehn)\s*jahr"), "10y"),
    (re.compile(r"\b(5|fünf|fuenf)\s*jahr"), "5y"),
    (re.compile(r"\b(1|einem?)\s*jahr|nächste[ns]?\s*jahr|naechste[ns]?\s*jahr"), "1y"),
    (re.compile(r"\bheute\b|\bjetzt\b|\bmomentan\b|diese[nm]?\s*monat"), "present"),
]
_INTENT_RES: list[tuple[re.Pattern[str], Intent]] = [
    # "wann" first: "Wann kann ich mir X leisten?" is a time_to_goal
    # question even though it also matches the affordability wording.
    (re.compile(r"\bwann\b|wie lange|bis ich"), "time_to_goal"),
    (re.compile(r"was wäre|was waere|wenn ich|angenommen|halbier|weniger für|weniger fuer|streich"), "what_if"),
    (re.compile(r"kann ich|reicht|leisten|schaffe ich|liegt.*drin"), "affordability"),
]
_LEASING_RE = re.compile(r"\bleasing\b|\brate[n]?\b|\bfinanzier")
_CASH_RE = re.compile(r"\bbar\b|\bcash\b|\beinmal")
_REDUCTION_RE = re.compile(r"(\d{1,3})\s*%|\bhalbier|\bhälfte|\bhaelfte")

# A purchase above this needs to know cash vs. leasing - below it the
# difference doesn't move the answer enough to be worth a round trip.
CLARIFY_PAYMENT_ABOVE_CHF = 10_000.0


class Extraction(NamedTuple):
    intent: Intent | None
    target_chf: float | None = None
    horizon: AssistantHorizon | None = None
    """Set only when the *text* names a horizon - it then overrides the switcher."""
    category: str | None = None
    reduction_pct: float | None = None
    payment_type: str | None = None


def _parse_amount(text: str) -> float | None:
    matches = _AMOUNT_RE.findall(text)
    candidates = []
    for raw in matches:
        cleaned = re.sub(r"[\s.'’]", "", raw) if re.search(r"[\s.'’]\d{3}", raw) else raw.replace(",", ".")
        try:
            candidates.append(float(cleaned))
        except ValueError:
            continue
    # Largest number wins: "in 5 Jahren ein Auto für 30'000" - the
    # horizon digit is always the smaller one.
    return max(candidates) if candidates else None


def extract(message: str, known_categories: list[str]) -> Extraction:
    text = message.lower()
    intent = next((i for pattern, i in _INTENT_RES if pattern.search(text)), None)
    if intent is None:
        return Extraction(intent=None)

    horizon = next((h for pattern, h in _HORIZON_RES if pattern.search(text)), None)
    reduction = _REDUCTION_RE.search(text)
    payment_type = "leasing" if _LEASING_RE.search(text) else "cash" if _CASH_RE.search(text) else None

    return Extraction(
        intent=intent,
        target_chf=_parse_amount(text),
        horizon=horizon,
        category=next((c for c in known_categories if c.lower() in text), None),
        reduction_pct=float(reduction.group(1)) if reduction and reduction.group(1) else (50.0 if reduction else None),
        payment_type=payment_type,
    )


def validate(extraction: Extraction, pending_clarification: str | None) -> Clarification | None:
    """At most one clarification per request - two make the live demo
    sluggish. A field that was just asked about is never asked again:
    the caller falls back to a documented default instead."""
    if extraction.intent == "what_if":
        return None
    if extraction.target_chf is None and pending_clarification != "target_chf":
        return Clarification(
            question="Um welchen Betrag geht es?",
            options=["CHF 5'000", "CHF 20'000", "CHF 30'000"],
            field="target_chf",
        )
    target = extraction.target_chf or 0.0
    if (
        extraction.intent == "affordability"
        and target >= CLARIFY_PAYMENT_ABOVE_CHF
        and extraction.payment_type is None
        and pending_clarification != "payment_type"
    ):
        return Clarification(question="Bar oder Leasing?", options=["Bar", "Leasing"], field="payment_type")
    return None
