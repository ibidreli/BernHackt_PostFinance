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
        raise AssistantLLMTimeoutError(ASSISTANT_LLM_TIMEOUT_SECONDS) from exc
    except openai.OpenAIError as exc:
        raise AssistantLLMError(f"Formulierung fehlgeschlagen: {exc}") from exc

    text = completion.choices[0].message.content
    if not text or not text.strip():
        raise AssistantLLMError("Formulierung lieferte keinen Text.")
    return text.strip()
