"""Zahlenabgleich (Feature #5, T10): verifies that every CHF- and
Monat(e)-labeled number in an LLM-generated answer text (`formulate_answer`,
T7) actually corresponds to a real value from `facts`/`levers` - the
issue's own explicit final safeguard: "Beträge werden nach der
Generierung gegen facts geprüft; bei Abweichung greift die
Template-Formulierung." On failure, `assistant_service.ask()` (T7) falls
back to `template_answer()` (T9) - reusing the same always-correct
deterministic formulation rather than building a second fallback
mechanism.

Motivated by a real bug found live-testing T7: `facts.buffer_after_months`
(a MONTHS value, 1.1) got described as "CHF 1" - the *number* was
present in `facts`, just attached to the wrong field/unit. A naive
"does this number appear anywhere in facts" check would NOT have caught
that (1 rounds from a real value, 1.1, that's genuinely in `facts` -
just not as a CHF amount). This module ties each parsed number to the
*unit word it was written with* (CHF vs. Monat/e) and compares against
the correspondingly-typed set of expected values, so a number can only
"count" as verified against a fact of the same kind.
"""

from __future__ import annotations

import re

from app.core.config import TIGHT_BUFFER_MONTHS
from app.schemas.assistant import AssistantFacts, Lever

_CHF_AMOUNT_RE = re.compile(r"CHF\s*(-?\d[\d']*(?:\.\d+)?)")
# German has three inflections after a count: "1 Monat" (singular), "3
# Monate" (plural nominative/accusative - no trailing "n"), "in 3 Monaten"
# (plural dative). The previous pattern only covered "Monat"/"Monaten" and
# silently ignored "Monate" - found live: a formulated answer with "17
# Monate warten" (a real, wrong number - the true wait_months was 14) went
# completely unmatched by this regex, so `verify_answer_text` never even
# looked at it and let a fabricated number through uncaught.
_MONTHS_AMOUNT_RE = re.compile(r"(-?\d[\d']*(?:\.\d+)?)\s*Monat(?:en|e)?\b")

# Wider for 5y/10y: the prompt instructs rounding to the nearest 100 for
# those horizons, and "nearest 100" can legitimately land up to 50 CHF
# either side of the raw value - 60 gives a little slack for the model's
# own rounding choice (floor/ceiling/nearest) without being so wide it
# stops catching real mistakes.
_CHF_TOLERANCE_ROUNDED = 60.0
_CHF_TOLERANCE_EXACT = 1.0
_MONTHS_TOLERANCE = 0.6  # covers "einem Monat" (1) vs. a raw 0.5-1.5 value


def _parse_number(raw: str) -> float:
    return float(raw.replace("'", ""))


def _expected_chf_values(facts: AssistantFacts, levers: list[Lever]) -> list[float]:
    values = [
        v
        for v in (
            facts.target_chf,
            facts.projected_chf,
            facts.gap_chf,
            facts.required_monthly_chf,
            facts.impact_monthly_chf,
            facts.impact_cumulative_chf,
        )
        if v is not None
    ]
    for lever in levers:
        values.append(lever.monthly_avg_chf)
        values.append(lever.potential_chf)
    return values


def _expected_month_values(facts: AssistantFacts) -> list[float]:
    values = [v for v in (facts.buffer_after_months, facts.wait_months, facts.months_remaining) if v is not None]
    if facts.wait_months is not None:
        # The formulation prompt now names the fixed target `wait_months`
        # counts down to (TIGHT_BUFFER_MONTHS, e.g. "bis der Puffer wieder
        # 3 Monate deckt") so the sentence isn't a dangling claim with no
        # anchor - that number must be accepted here too, or a correctly
        # instructed LLM answer would fail verification and get discarded
        # for no reason.
        values.append(TIGHT_BUFFER_MONTHS)
    return values


def _matches_any(value: float, expected: list[float], tolerance: float) -> bool:
    return any(abs(value - e) <= tolerance for e in expected)


def verify_answer_text(text: str, facts: AssistantFacts, levers: list[Lever], horizon: str) -> bool:
    """`True` if every CHF-labeled and every Monat(e)-labeled number in
    `text` is close enough to *some* real value from `facts`/`levers` of
    the matching kind - `False` means `assistant_service.ask()` (T7)
    should discard `text` and use `template_answer()` instead."""
    chf_tolerance = _CHF_TOLERANCE_ROUNDED if horizon in ("5y", "10y") else _CHF_TOLERANCE_EXACT
    expected_chf = _expected_chf_values(facts, levers)
    expected_months = _expected_month_values(facts)

    for match in _CHF_AMOUNT_RE.finditer(text):
        value = _parse_number(match.group(1))
        if not _matches_any(value, expected_chf, chf_tolerance):
            return False

    for match in _MONTHS_AMOUNT_RE.finditer(text):
        value = _parse_number(match.group(1))
        if not _matches_any(value, expected_months, _MONTHS_TOLERANCE):
            return False

    return True
