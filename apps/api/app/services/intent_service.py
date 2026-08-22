"""Intent extraction + validation (Feature #5, T3) - "LLM-Call #1" from
the issue's architecture diagram.

    Nutzerfrage -> LLM (Extraktion) -> strukturierte Parameter
                -> Validierung -> Parameter plausibel? sonst Rückfrage

This module owns exactly those first two boxes. It never touches
`forecast_service`, never sees a raw transaction, and never decides the
final `yes`/`tight`/`no_unless` answer - that's T5, built on top of
`ExtractedIntent` once `validate_extraction()` says `status="ok"`.

Three things live here on purpose, not split across files:
1. `ExtractedIntent` - the LLM's Structured Output schema. Raw signals
   only ("what was said"), not decisions.
2. `extract_intent()` - the actual OpenAI call (Structured Outputs via
   `beta.chat.completions.parse`), with the `ASSISTANT_LLM_TIMEOUT_SECONDS`
   timeout enforced and turned into an explicit exception on failure -
   per your instruction, NOT a silent fallback that pretends to work.
3. `validate_extraction()` / `apply_clarification_answer()` - the
   deterministic clarification/unsupported ladder. The issue is explicit
   that Rückfragen are "fest definiert, nicht vom Modell erfunden" - so
   the fixed table below, not the LLM, decides wording and options.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Literal, NamedTuple

import openai
from openai import OpenAI
from pydantic import BaseModel, Field

from app.core.config import (
    ASSISTANT_LLM_TIMEOUT_SECONDS,
    LARGE_PURCHASE_THRESHOLD_CHF,
    OPENAI_API_KEY,
    OPENAI_MODEL,
)
from app.schemas.assistant import AssistantHorizon, Clarification

_PROMPT_PATH = Path(__file__).resolve().parent.parent / "prompts" / "intent_extraction_v1.md"
_SYSTEM_PROMPT = _PROMPT_PATH.read_text(encoding="utf-8")


class AssistantLLMError(Exception):
    """Base class for any LLM-call failure in this feature (extraction
    here in T3, formulation in T10). The API layer (T11) turns this into
    an explicit error response for the user - never a silent fallback."""


class AssistantLLMTimeoutError(AssistantLLMError):
    def __init__(self, seconds: float):
        self.seconds = seconds
        super().__init__(f"LLM-Call hat das Timeout von {seconds}s überschritten.")


# --- ExtractedIntent: LLM Structured Output ------------------------------


class ExtractedIntent(BaseModel):
    """LLM call #1's Structured Output. Every field is optional/nullable
    by design (OpenAI Structured Outputs strict mode requires all
    properties present in the schema, but nullable ones may come back
    `null`) - `null` means "not mentioned in the text", which is exactly
    what `validate_extraction()` needs to decide on a clarification.
    """

    intent: Literal["affordability", "what_if", "time_to_goal", "unsupported"]
    horizon_override: AssistantHorizon | None = Field(
        default=None,
        description="Nur gesetzt, wenn der Text selbst einen Zeitraum nennt, der vom Umschalter abweicht "
        '(z.B. "in 5 Jahren"). null, wenn kein Zeitraum im Text genannt wird - der Umschalter-Wert gilt dann.',
    )
    target_chf: float | None = Field(default=None, description="Zielbetrag in CHF, falls genannt.")
    target_label: str | None = Field(default=None, description="Kurzes Label für das Ziel, z.B. 'Auto', 'Ferien'.")
    category_percent_hint: bool = Field(
        default=False,
        description='true, wenn die Frage eine prozentuale Änderung einer ganzen Kategorie beschreibt '
        '("Kantine halbieren") statt eines konkreten Postens - technisch nicht abbildbar, siehe Prompt.',
    )
    adjustment_kind: Literal["cancel", "adjust", "add", "one_off"] | None = Field(
        default=None, description="Nur bei what_if: welcher der 4 Anpassungstypen gemeint ist."
    )
    merchant_hint: str | None = Field(
        default=None, description="Freitext-Name des betroffenen Abos/Postens, z.B. 'Netflix'."
    )
    delta_chf: float | None = Field(default=None, description="Betrags-Änderung bei adjust, z.B. +200.")
    amount_chf: float | None = Field(default=None, description="Betrag bei add/one_off.")
    payment_type: Literal["cash", "leasing"] | None = Field(
        default=None, description='Nur gesetzt, falls im Text genannt ("bar", "leasing").'
    )


# --- LLM call ------------------------------------------------------------

_client: OpenAI | None = None


def _get_client() -> OpenAI:
    global _client
    if _client is None:
        _client = OpenAI(api_key=OPENAI_API_KEY)
    return _client


def extract_intent(
    message: str,
    horizon: AssistantHorizon,
    prior_turn_summary: str | None = None,
) -> ExtractedIntent:
    """LLM call #1. `prior_turn_summary` is an optional short digest of
    the previous question/answer for follow-up resolution (T4/T7 build
    this - kept as a plain string here so extraction stays decoupled from
    the conversation-state storage mechanism).

    Raises `AssistantLLMTimeoutError`/`AssistantLLMError` on failure -
    callers must surface this as an explicit error, not guess.
    """
    user_content = f"Horizont-Umschalter (aktuell gewählt): {horizon}\n\n"
    if prior_turn_summary:
        user_content += f"Vorheriger Gesprächsverlauf (für Folgefragen):\n{prior_turn_summary}\n\n"
    user_content += f"Frage: {message}"

    try:
        completion = _get_client().beta.chat.completions.parse(
            model=OPENAI_MODEL,
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": user_content},
            ],
            response_format=ExtractedIntent,
            timeout=ASSISTANT_LLM_TIMEOUT_SECONDS,
        )
    except openai.APITimeoutError as exc:
        raise AssistantLLMTimeoutError(ASSISTANT_LLM_TIMEOUT_SECONDS) from exc
    except openai.OpenAIError as exc:
        raise AssistantLLMError(f"Extraktion fehlgeschlagen: {exc}") from exc

    parsed = completion.choices[0].message.parsed
    if parsed is None:
        # Model refused or produced something that didn't fit the schema
        # at all (rare with strict Structured Outputs, but the SDK models
        # it as `parsed is None` rather than raising - handle it).
        raise AssistantLLMError("Extraktion lieferte kein verwertbares Ergebnis.")
    return parsed


# --- Fixed clarification table (issue: "fest definiert, nicht vom Modell
# erfunden") --------------------------------------------------------------

_FIXED_CLARIFICATIONS: dict[str, Clarification] = {
    "target_chf": Clarification(
        question="Welcher Betrag ungefähr?",
        options=[],  # Freitext - ein Betrag ist keine sinnvolle Button-Auswahl.
        field="target_chf",
    ),
    "horizon": Clarification(
        question="Wann ungefähr?", options=["1 Jahr", "5 Jahre", "10 Jahre"], field="horizon"
    ),
    "payment_type": Clarification(question="Bar oder Leasing?", options=["Bar", "Leasing"], field="payment_type"),
    "recurrence": Clarification(
        question="Einmalig oder monatlich?", options=["Einmalig", "Monatlich"], field="recurrence"
    ),
}


class ValidationResult(NamedTuple):
    status: Literal["ok", "needs_clarification", "unsupported"]
    clarification: Clarification | None
    reason: str | None  # internal/log-facing, e.g. for STATUS/debugging - not necessarily shown verbatim


def validate_extraction(extracted: ExtractedIntent, request_horizon: AssistantHorizon) -> ValidationResult:
    """Deterministic ladder, evaluated in this exact priority order so
    at most ONE clarification is ever triggered per request (issue:
    "Maximal eine Rückfrage pro Anfrage") - target amount first (nothing
    else is computable without it), then timeframe, then payment type,
    then what_if specifics.
    """
    if extracted.intent == "unsupported":
        return ValidationResult("unsupported", None, "LLM hat die Frage keinem der drei Typen zugeordnet.")

    if extracted.intent == "what_if" and extracted.category_percent_hint:
        # Team decision (STATUS.md): "Kantine halbieren"-artige Fragen
        # bleiben unsupported, kein 5. Adjustment-Typ.
        return ValidationResult(
            "unsupported", None, "Kategorie-Prozent-Anpassung, mit keinem der 4 Adjustment-Typen abbildbar."
        )

    if extracted.intent in ("affordability", "time_to_goal") and extracted.target_chf is None:
        return ValidationResult("needs_clarification", _FIXED_CLARIFICATIONS["target_chf"], None)

    if (
        extracted.intent in ("affordability", "time_to_goal")
        and extracted.horizon_override is None
        and request_horizon == "present"
    ):
        # "present" beantwortet nur die Gegenwart (issue: "die einzige
        # Stufe ohne Annahmen") - eine vorwärtsgerichtete Frage ohne
        # erkennbaren Zeitraum braucht erst einen Horizont, bevor
        # forecast_service überhaupt sinnvoll aufgerufen werden kann.
        return ValidationResult("needs_clarification", _FIXED_CLARIFICATIONS["horizon"], None)

    if (
        extracted.intent == "affordability"
        and extracted.target_chf is not None
        and extracted.target_chf >= LARGE_PURCHASE_THRESHOLD_CHF
        and extracted.payment_type is None
    ):
        return ValidationResult("needs_clarification", _FIXED_CLARIFICATIONS["payment_type"], None)

    if extracted.intent == "what_if":
        if extracted.adjustment_kind in ("cancel", "adjust") and not extracted.merchant_hint:
            # Kein Rückfrage-Typ dafür im fest definierten Set - bewusst
            # nicht selbständig um einen 5. Trigger erweitert (siehe
            # ASSISTANT_STATUS.md, T3).
            return ValidationResult(
                "unsupported", None, "Kein erkennbarer Abo-/Postenname für cancel/adjust extrahiert."
            )
        if extracted.adjustment_kind is None:
            return ValidationResult("needs_clarification", _FIXED_CLARIFICATIONS["recurrence"], None)

    return ValidationResult("ok", None, None)


# --- Applying a clarification answer (no LLM call needed) ---------------

_ANSWER_MAPPERS: dict[str, dict[str, object]] = {
    "payment_type": {"bar": "cash", "leasing": "leasing"},
    "horizon": {"1 jahr": "1y", "5 jahre": "5y", "10 jahre": "10y"},
    "recurrence": {"einmalig": "one_off", "monatlich": "add"},
}

_DEFAULTS_ON_IGNORE: dict[str, object] = {
    # Issue: "Wird die Rückfrage ignoriert, rechnet der Bot mit dem
    # Default und schreibt dazu, welchen er genommen hat." These are that
    # default - `apply_clarification_answer` reports whether one was used
    # so the caller (T7) can put it in the answer text.
    "payment_type": "cash",  # einfacherer Pfad (one_off) statt Leasing-Annahme
    "recurrence": "one_off",  # keine laufende Verpflichtung unterstellen, die nicht klar gemeint war
}

_AMOUNT_RE = re.compile(r"\d+(?:[.,]\d+)?")


def _parse_amount(text: str) -> float | None:
    cleaned = text.replace("'", "").replace("’", "")
    match = _AMOUNT_RE.search(cleaned)
    if not match:
        return None
    return float(match.group(0).replace(",", "."))


class ClarificationAnswer(NamedTuple):
    extracted: ExtractedIntent
    default_used: str | None  # e.g. "Bar" if the user's answer couldn't be matched and a default was applied


def apply_clarification_answer(previous: ExtractedIntent, field: str, answer_text: str) -> ClarificationAnswer:
    """Deterministic, no LLM call - clarification answers are always one
    of the small fixed set of button labels defined in
    `_FIXED_CLARIFICATIONS` (issue: "immer mit Antwortvorschlägen als
    Buttons"), so parsing them doesn't need one. Free-text answers that
    don't match a button (user typed instead of clicking, or clicked
    something unexpected) fall back to `_DEFAULTS_ON_IGNORE` - `field`
    "target_chf" has no default (there's no sane number to guess), so an
    unparseable amount answer leaves `target_chf` unset; the caller (T7)
    should then treat that as `unsupported` rather than loop into a
    second clarification (issue: max one Rückfrage per request).
    """
    if field == "target_chf":
        parsed = _parse_amount(answer_text)
        if parsed is not None:
            return ClarificationAnswer(previous.model_copy(update={"target_chf": parsed}), None)
        return ClarificationAnswer(previous, None)

    mapping = _ANSWER_MAPPERS.get(field, {})
    matched = mapping.get(answer_text.strip().lower())
    default_used: str | None = None

    if matched is None:
        default = _DEFAULTS_ON_IGNORE.get(field)
        if default is None:
            return ClarificationAnswer(previous, None)
        matched = default
        # Report the *German* label of the default that was actually
        # applied, not the internal machine value, so T7 can drop it
        # straight into the answer text ("...ich habe Bar angenommen").
        label_by_value = {v: k for k, v in mapping.items()}
        default_used = label_by_value.get(matched, str(matched)).capitalize()

    updates: dict[str, object] = {}
    if field == "payment_type":
        updates["payment_type"] = matched
    elif field == "horizon":
        updates["horizon_override"] = matched
    elif field == "recurrence":
        updates["adjustment_kind"] = matched

    return ClarificationAnswer(previous.model_copy(update=updates) if updates else previous, default_used)
