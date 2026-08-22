"""Orchestration (Feature #5, T7) - implements the issue's full
architecture diagram end to end:

    Nutzerfrage
      -> LLM (Extraktion)      T3
      -> Validierung           T3
      -> forecast_service      T2 / Feature #4
      -> Antwortlogik          T5
      -> LLM (Formulierung)    T7 (this module) / T8 prompt / T10 check
      -> Chart-Auswahl         T6

Also owns Folgefragen/multi-turn Rückfragen (T4's `ConversationStore`):
an incoming message either answers a still-open clarification (no LLM
call #1 needed - `apply_clarification_answer` is deterministic) or is a
fresh question, optionally with a previous turn's context folded into
extraction via `prior_turn_summary`.

Two response paths never call LLM #2 (formulation) at all:
`needs_clarification` (the fixed question IS the answer) and
`unsupported` (a fixed, code-written text naming the three supported
question types - issue: not a model's job to invent this). Only a fully
resolved `ok` computation goes through formulation.
"""

from __future__ import annotations

import logging
from datetime import date

from app.core.config import ASSISTANT_MODE
from app.models.recurring_payment import RecurringPayment
from app.models.transaction import Transaction
from app.repositories.balance_repository import BalanceRepository
from app.schemas.assistant import AssistantAskRequest, AssistantAskResponse, AssistantFacts
from app.services.answer_service import (
    UnresolvedAdjustmentError,
    answer_affordability,
    answer_time_to_goal,
    answer_what_if,
)
from app.services.cache_service import CACHED_QUESTIONS, match_cached_question
from app.services.chart_service import build_chart
from app.services.classification import Classification
from app.services.conversation_state import (
    ConversationState,
    ConversationStore,
    build_prior_turn_summary,
    resolve_pending_clarification,
)
from app.services.formulation_service import FormulationInput, formulate_answer, template_answer
from app.services.intent_service import extract_intent, validate_extraction
from app.services.intent_service import apply_clarification_answer as _apply_clarification_answer
from app.services.verification_service import verify_answer_text

logger = logging.getLogger(__name__)

_UNSUPPORTED_SUFFIX = (
    "Ich kann bei drei Dingen helfen: ob du dir etwas leisten kannst, was eine Änderung an einer "
    "wiederkehrenden Zahlung bewirkt, oder wann du ein Sparziel erreichst."
)

_CACHED_NO_MATCH_PREFIX = "Im Offline-Modus sind nur die vorbereiteten Demo-Fragen verfügbar: " + " / ".join(
    f'"{q.text}"' for q in CACHED_QUESTIONS
)


def _unsupported_response(prefix: str | None = None, source: str = "live") -> AssistantAskResponse:
    answer = f"{prefix} {_UNSUPPORTED_SUFFIX}" if prefix else _UNSUPPORTED_SUFFIX
    return AssistantAskResponse(
        intent="unsupported",
        status="unsupported",
        answer=answer,
        facts=None,
        levers=[],
        chart=None,
        assumptions_used=None,
        clarification=None,
        source=source,
    )


def _describe_adjustment(extracted) -> str | None:
    """Deterministic, code-written description of what a `what_if`
    adjustment actually does - fed into LLM call #2 verbatim so it
    describes the right *action*, not something inferred from the sign
    of `impact_monthly_chf` alone. Found via live testing (T7): without
    this, a Netflix *cancellation* (a positive/good impact) got narrated
    as an "Erhöhung" (increase) of Netflix spending - numerically the
    text still matched `facts`, but the described action was simply
    wrong. `None` for non-what_if intents."""
    if extracted.intent != "what_if":
        return None
    label = extracted.merchant_hint or "diesen Posten"
    kind = extracted.adjustment_kind
    if kind == "cancel":
        return f'"{label}" wird gekündigt und entfällt komplett.'
    if kind == "adjust":
        delta = extracted.delta_chf or 0.0
        direction = "erhöht" if delta >= 0 else "reduziert"
        return f'"{label}" wird um CHF {abs(delta):,.0f} {direction}.'.replace(",", "'")
    if kind == "add":
        amount = extracted.amount_chf or extracted.delta_chf or 0.0
        return f'Eine neue monatliche Ausgabe "{label}" von CHF {amount:,.0f} kommt hinzu.'.replace(",", "'")
    if kind == "one_off":
        amount = extracted.amount_chf or 0.0
        return f'Eine einmalige Ausgabe "{label}" von CHF {amount:,.0f} wird getätigt.'.replace(",", "'")
    return None


def _facts_summary_text(facts: AssistantFacts) -> str | None:
    """Short digest stored in `ConversationState.last_facts_summary` for
    follow-up resolution (T4's `build_prior_turn_summary`) - not shown to
    the user directly."""
    parts: list[str] = []
    if facts.gap_chf is not None:
        parts.append(f"Fehlbetrag CHF {facts.gap_chf:,.0f}".replace(",", "'"))
    if facts.required_monthly_chf is not None:
        parts.append(f"nötig CHF {facts.required_monthly_chf:,.0f}/Monat mehr".replace(",", "'"))
    if facts.buffer_after_months is not None:
        parts.append(f"Restpuffer {facts.buffer_after_months} Monatsausgaben")
    if facts.wait_months is not None:
        parts.append(f"Wartezeit {facts.wait_months} Monate")
    if facts.goal_date is not None:
        parts.append(f"erreichbar am {facts.goal_date.isoformat()}")
    if facts.impact_monthly_chf is not None:
        parts.append(f"Wirkung CHF {facts.impact_monthly_chf:,.0f}/Monat".replace(",", "'"))
    return ", ".join(parts) if parts else None


def ask(
    request: AssistantAskRequest,
    transactions: list[Transaction],
    recurring_payments: list[RecurringPayment],
    classifications: list[Classification],
    balance_repo: BalanceRepository,
    conversation_store: ConversationStore,
    as_of: date | None = None,
    mode: str | None = None,
) -> AssistantAskResponse:
    """Raises `AssistantLLMTimeoutError`/`AssistantLLMError` (from
    `app.services.llm_client`) if either LLM call fails in `mode="live"`
    - callers (T11) must turn that into an explicit error response,
    never a silent fallback that looks like a normal answer (your
    instruction). `mode="cached"` (T9) makes neither LLM call at all -
    see `app.services.cache_service`/`template_answer` - so it can't
    raise these.

    `mode=None` (the default) reads the configured `ASSISTANT_MODE` at
    call time, not import time - read fresh from `app.core.config` each
    call rather than frozen as a parameter default, so it reflects the
    actual running configuration even under test/hot-reload.
    """
    if as_of is None:
        as_of = date.today()
    if mode is None:
        mode = ASSISTANT_MODE

    conversation_id = request.context.conversation_id if request.context else None
    context_pending_field = request.context.pending_clarification if request.context else None
    state = conversation_store.get(conversation_id)

    clarification_field = resolve_pending_clarification(state, context_pending_field, request.message)
    default_note: str | None = None

    if clarification_field is not None:
        # Answering an open Rückfrage - deterministic, no LLM call #1
        # (issue: buttons, not free-form parsing) - see T3/T4.
        assert state is not None  # resolve_pending_clarification only returns non-None when state has one
        answer = _apply_clarification_answer(state.last_extracted, clarification_field, request.message)
        extracted = answer.extracted
        if answer.default_used is not None:
            default_note = f"Rückfrage nicht eindeutig beantwortet - angenommen: {answer.default_used}."

        # No second Rückfrage (issue: max one per request) - the one gap
        # that would still block computation (missing amount) becomes
        # unsupported instead of looping.
        if extracted.intent in ("affordability", "time_to_goal") and extracted.target_chf is None:
            if conversation_id:
                conversation_store.clear(conversation_id)
            return _unsupported_response("Ich konnte den Betrag weiterhin nicht erkennen.", source=mode)

        resolved_horizon = extracted.horizon_override or state.last_horizon
    else:
        if mode == "cached":
            # T9: no LLM call #1 at all - exact match against the fixed
            # demo-question set (app.services.cache_service).
            cached = match_cached_question(request.message)
            if cached is None:
                if conversation_id:
                    conversation_store.clear(conversation_id)
                return _unsupported_response(_CACHED_NO_MATCH_PREFIX, source=mode)
            extracted = cached.extracted
        else:
            prior_summary = build_prior_turn_summary(state) if state else None
            extracted = extract_intent(request.message, request.horizon, prior_turn_summary=prior_summary)

        validation = validate_extraction(extracted, request.horizon)

        if validation.status == "unsupported":
            if conversation_id:
                conversation_store.clear(conversation_id)
            return _unsupported_response(source=mode)

        if validation.status == "needs_clarification":
            assert validation.clarification is not None
            if conversation_id:
                conversation_store.save(
                    ConversationState(
                        conversation_id=conversation_id,
                        last_message=request.message,
                        last_extracted=extracted,
                        last_horizon=extracted.horizon_override or request.horizon,
                        last_intent=extracted.intent,
                        last_status="needs_clarification",
                        last_facts_summary=None,
                        pending_clarification=validation.clarification,
                    )
                )
            return AssistantAskResponse(
                intent=extracted.intent,
                status="needs_clarification",
                answer=validation.clarification.question,
                facts=None,
                levers=[],
                chart=None,
                assumptions_used=None,
                clarification=validation.clarification,
                source=mode,
            )

        resolved_horizon = extracted.horizon_override or request.horizon

    # --- T5: Antwortlogik ---------------------------------------------
    try:
        if extracted.intent == "affordability":
            result = answer_affordability(
                extracted, resolved_horizon, as_of, transactions, recurring_payments, classifications, balance_repo, request.assumptions
            )
        elif extracted.intent == "time_to_goal":
            result = answer_time_to_goal(
                extracted, resolved_horizon, as_of, transactions, recurring_payments, classifications, balance_repo, request.assumptions
            )
        elif extracted.intent == "what_if":
            result = answer_what_if(
                extracted, resolved_horizon, as_of, transactions, recurring_payments, classifications, balance_repo, request.assumptions
            )
        else:  # pragma: no cover - validate_extraction already filtered "unsupported" out above
            if conversation_id:
                conversation_store.clear(conversation_id)
            return _unsupported_response(source=mode)
    except UnresolvedAdjustmentError as exc:
        if conversation_id:
            conversation_store.clear(conversation_id)
        return _unsupported_response(str(exc), source=mode)

    # --- T6: Chart-Auswahl ----------------------------------------------
    chart = build_chart(extracted.intent, result)

    # --- LLM call #2: Formulierung (T9: template statt LLM in cached-Modus) ---
    formulation_input = FormulationInput(
        intent=extracted.intent,
        status=result.status,
        horizon=resolved_horizon,
        target_label=extracted.target_label,
        merchant_label=extracted.merchant_hint,
        adjustment_description=_describe_adjustment(extracted),
        facts=result.facts,
        levers=result.levers,
        assumptions_used=result.assumptions_used,
        default_used_note=default_note,
    )
    if mode == "cached":
        answer_text = template_answer(formulation_input)
    else:
        answer_text = formulate_answer(formulation_input)
        # T10: Zahlenabgleich - issue's own final safeguard. Falls back
        # to the same always-correct template used for cached mode (T9)
        # rather than a second bespoke mechanism. Doesn't change `source`
        # ("live" stays accurate - the computation was live either way,
        # only the wording's origin silently changes) but is logged so
        # it's visible during QA/the pitch if it ever fires.
        if not verify_answer_text(answer_text, result.facts, result.levers, resolved_horizon):
            logger.warning("Zahlenabgleich fehlgeschlagen, Fallback auf Template-Formulierung: %r", answer_text)
            answer_text = template_answer(formulation_input)

    if conversation_id:
        conversation_store.save(
            ConversationState(
                conversation_id=conversation_id,
                last_message=request.message,
                last_extracted=extracted,
                last_horizon=resolved_horizon,
                last_intent=extracted.intent,
                last_status=result.status,
                last_facts_summary=_facts_summary_text(result.facts),
                pending_clarification=None,
            )
        )

    return AssistantAskResponse(
        intent=extracted.intent,
        status=result.status,
        answer=answer_text,
        facts=result.facts,
        levers=result.levers,
        chart=chart,
        assumptions_used=result.assumptions_used,
        clarification=None,
        source=mode,
    )
