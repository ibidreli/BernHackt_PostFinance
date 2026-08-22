"""Answer formulation - LLM call #2 in the issue's architecture diagram
(Feature #5, built as part of T7; polished/reviewed as T8, verified
against `facts` as T9/T10).

Takes the already-finished result (`FormulationInput` - status, facts,
levers, assumptions_used) and turns it into prose. Never sees a raw
transaction and never computes anything - matches T3's extraction module
in spirit, just the mirror-image direction (structured-in/text-out here,
vs. text-in/structured-out there).
"""

from __future__ import annotations

from pathlib import Path

import openai
from pydantic import BaseModel, Field

from app.core.config import ASSISTANT_LLM_TIMEOUT_SECONDS, OPENAI_MODEL
from app.schemas.assistant import AnswerStatus, AssistantFacts, AssistantHorizon, AssumptionsUsed, Lever, ResponseIntent
from app.services.llm_client import AssistantLLMError, AssistantLLMTimeoutError, get_client

_PROMPT_PATH = Path(__file__).resolve().parent.parent / "prompts" / "answer_formulation_v1.md"
_SYSTEM_PROMPT = _PROMPT_PATH.read_text(encoding="utf-8")


class FormulationInput(BaseModel):
    """Exactly what LLM call #2 sees - the issue's "beim zweiten Mal nur
    das fertige Ergebnisobjekt". Serialized to JSON as the user message."""

    intent: ResponseIntent
    status: AnswerStatus
    horizon: AssistantHorizon
    target_label: str | None = None
    merchant_label: str | None = None
    adjustment_description: str | None = Field(
        default=None,
        description="Nur bei what_if: was genau geändert wird, in Worten (z.B. 'Netflix wird gekündigt') - "
        "fest vorgegeben, damit das Modell die Richtung der Änderung nicht aus dem Vorzeichen von "
        "impact_monthly_chf erraten muss (gefundener Bug: eine Kündigung wurde als 'Erhöhung' beschrieben, "
        "siehe ASSISTANT_STATUS.md T7).",
    )
    facts: AssistantFacts
    levers: list[Lever]
    assumptions_used: AssumptionsUsed
    default_used_note: str | None = None


def formulate_answer(input_data: FormulationInput) -> str:
    """Raises `AssistantLLMTimeoutError`/`AssistantLLMError` on failure -
    per your decision, callers (T11) must surface this as an explicit
    error, never silently substitute template text."""
    try:
        completion = get_client().chat.completions.create(
            model=OPENAI_MODEL,
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": input_data.model_dump_json(exclude_none=True)},
            ],
            timeout=ASSISTANT_LLM_TIMEOUT_SECONDS,
        )
    except openai.APITimeoutError as exc:
        raise AssistantLLMTimeoutError(ASSISTANT_LLM_TIMEOUT_SECONDS, stage="Formulierung") from exc
    except openai.OpenAIError as exc:
        raise AssistantLLMError(f"Formulierung fehlgeschlagen: {exc}") from exc

    text = completion.choices[0].message.content
    if not text or not text.strip():
        raise AssistantLLMError("Formulierung lieferte keinen Text.")
    return text.strip()


# --- Template-Formulierung (T9, ASSISTANT_MODE=cached) ---------------------


def _chf(amount: float | None, round_100: bool) -> str | None:
    if amount is None:
        return None
    value = round(amount / 100) * 100 if round_100 else round(amount)
    return f"CHF {value:,.0f}".replace(",", "'")


def _months_phrase(n: float | None) -> str | None:
    if n is None:
        return None
    n_int = round(n)
    return "einem Monat" if n_int == 1 else f"{n_int} Monaten"


def _impact_phrase(f: AssistantFacts, round_100: bool) -> str:
    """Sign-aware wording for a what_if impact - found via live testing
    (T9): a negative impact (a change that costs money, e.g. a new
    recurring expense) rendered as "die Bilanz verbessert sich um CHF
    -50", which is both grammatically odd and misleading (reads like an
    improvement). "verbessert"/"verschlechtert" + the absolute amount
    reads correctly either way.

    Falls back to the monthly-equivalent rate (`impact_monthly_chf`) when
    the cumulative total (`impact_cumulative_chf`) is exactly 0 - found
    live: "Netflix kündigen" asked at `present` with `as_of` a few days
    before the next payday returned "verbessert deine Bilanz über den
    Zeitraum um CHF 0" verbatim, even though cancelling Netflix is a real
    CHF 29.90/month saving. `present` reuses Feature #4's `next_salary`
    horizon (see `answer_service.answer_what_if`), which can be as short
    as 1-2 days - a monthly subscription's exact billing date only rarely
    falls inside that narrow window, so `impact_cumulative_chf` (the
    literal balance difference at that window's end) is legitimately 0
    almost every time this is asked shortly after payday, independent of
    whether the subscription is real. `impact_monthly_chf` is the
    window-independent, always-correct rate for recurring adjustments and
    stays 0 for genuinely non-recurring ones (`one_off`, see
    `forecast_service._monthly_equivalent_impact`), so this fallback never
    fires for those - the cumulative total remains the right (and only
    meaningful) number there."""
    cumulative = f.impact_cumulative_chf or 0.0
    if cumulative == 0.0 and f.impact_monthly_chf:
        verb = "spart" if f.impact_monthly_chf >= 0 else "kostet"
        return f"Das {verb} dir {_chf(abs(f.impact_monthly_chf), False)} pro Monat."
    verb = "verbessert" if cumulative >= 0 else "verschlechtert"
    return f"Das {verb} deine Bilanz über den Zeitraum um {_chf(abs(cumulative), round_100)}."


def template_answer(input_data: FormulationInput) -> str:
    """Deterministic alternative to `formulate_answer()` - no LLM call at
    all. Used when `ASSISTANT_MODE=cached` (T9): every number is read
    directly out of `facts`/`levers` via plain string formatting, so by
    construction nothing here can ever contradict the numbers shown
    elsewhere in the response (unlike the LLM path in `formulate_answer`,
    which is why T10's verification step exists specifically for that
    path, not this one).

    Deliberately mirrors the same content rules as
    `answer_formulation_v1.md` (which status mentions which facts, CHF
    rounding to 100 for 5y/10y, months not CHF for buffer/wait) so the
    two paths read consistently to a user who doesn't know which one
    answered - see ASSISTANT_STATUS.md T9 for why "nichts wird
    vorgetäuscht, was nicht funktioniert" (issue's own phrase) matters
    here: the *numbers* are always the real, live-computed ones, only
    the LLM call is skipped.
    """
    f = input_data.facts
    round_100 = input_data.horizon in ("5y", "10y")
    chf = lambda amount: _chf(amount, round_100)  # noqa: E731

    sentences: list[str] = []

    if input_data.intent == "what_if" and input_data.adjustment_description:
        sentences.append(input_data.adjustment_description)

    if input_data.status == "yes":
        if input_data.intent == "what_if" and f.impact_cumulative_chf is not None:
            sentences.append(_impact_phrase(f, round_100))
        elif f.projected_chf is not None:
            sentences.append(f"Das ist gut möglich - du hast voraussichtlich {chf(f.projected_chf)} zur Verfügung.")
        if f.buffer_after_months is not None:
            sentences.append(f"Danach bleibt dir ein Puffer von rund {_months_phrase(f.buffer_after_months)}.")

    elif input_data.status == "tight":
        if input_data.intent == "what_if" and f.impact_cumulative_chf is not None:
            sentences.append("Das reicht knapp. " + _impact_phrase(f, round_100))
        elif f.projected_chf is not None:
            sentences.append(f"Das reicht knapp - du hast voraussichtlich {chf(f.projected_chf)} zur Verfügung.")
        if f.buffer_after_months is not None:
            sentences.append(f"Der Puffer danach liegt bei nur rund {_months_phrase(f.buffer_after_months)}.")
        if f.wait_months is not None:
            sentences.append(f"Mit etwas mehr Geduld - rund {_months_phrase(f.wait_months)} - würde der Puffer wieder reichen.")

    elif input_data.status == "no_unless":
        if f.gap_chf is not None:
            sentences.append(f"Das reicht nicht - es fehlen {chf(f.gap_chf)}.")
        if f.required_monthly_chf is not None:
            sentences.append(f"Dafür wären zusätzlich {chf(f.required_monthly_chf)} pro Monat nötig.")
        if input_data.levers:
            lever = input_data.levers[0]
            category = lever.category.replace(" // ", " - ")
            sentences.append(
                f"Ein möglicher Hebel: bei {category} liegt das Sparpotenzial bei rund "
                f"{chf(lever.potential_chf)} pro Monat."
            )

    if input_data.intent == "time_to_goal" and f.goal_date is not None:
        sentences.append(f"Erwartetes Datum: {f.goal_date.strftime('%d.%m.%Y')}.")

    if input_data.default_used_note:
        sentences.append(input_data.default_used_note)

    if not sentences:
        sentences.append("Die Berechnung liegt vor, aber es gibt aktuell keine weiteren Details dazu.")

    return " ".join(sentences)
