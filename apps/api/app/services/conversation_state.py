"""Conversation state (Feature #5, T4): in-memory per-`conversation_id`
store that makes two things possible:

1. **Folgefragen** (issue's own "offene Frage", decided: in scope) - "Und
   wenn ich 2 Jahre länger warte?" only makes sense if something
   remembers what "2 Jahre länger" is relative to. `build_prior_turn_summary()`
   turns the last turn into a short text digest that T7 feeds into
   `intent_service.extract_intent()`'s `prior_turn_summary` parameter.
2. **Multi-turn clarification answering** - `resolve_pending_clarification()`
   decides whether an incoming message is answering a still-open
   Rückfrage or is a fresh question, so T7 knows whether to call
   `intent_service.apply_clarification_answer()` or `extract_intent()`.

No database (project-wide decision): a plain dict, wrapped in a small
class so the *behavior* has one place to live even though the storage
itself is trivial. Lost on restart, no TTL/cleanup - accepted for a
hackathon demo's request volume, see ASSISTANT_STATUS.md T4. Not
thread-safe against two concurrent requests for the *same*
`conversation_id` (last write wins) - a real race, but a vanishingly
unlikely one in a live pitch demo with one person typing.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timezone

from app.schemas.assistant import AnswerStatus, AssistantHorizon, Clarification, ResponseIntent
from app.services.intent_service import ExtractedIntent


@dataclass
class ConversationState:
    conversation_id: str
    last_message: str
    last_extracted: ExtractedIntent
    """The *final* parameters actually used for the last turn's forecast
    call - i.e. after any clarification answer was already merged in, not
    the raw first-pass extraction. This is what a follow-up question
    should be understood relative to."""
    last_horizon: AssistantHorizon
    last_intent: ResponseIntent
    last_status: AnswerStatus
    last_facts_summary: str | None
    pending_clarification: Clarification | None
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


class ConversationStore:
    def __init__(self) -> None:
        self._states: dict[str, ConversationState] = {}

    def get(self, conversation_id: str | None) -> ConversationState | None:
        if not conversation_id:
            return None
        return self._states.get(conversation_id)

    def save(self, state: ConversationState) -> None:
        self._states[state.conversation_id] = state

    def clear(self, conversation_id: str) -> None:
        self._states.pop(conversation_id, None)

    def __len__(self) -> int:  # for /health-style introspection
        return len(self._states)


def build_prior_turn_summary(state: ConversationState) -> str:
    """Short natural-language digest for LLM call #1's `prior_turn_summary`
    parameter - plain text, not JSON, since it's context for the model to
    read, not a machine contract T7 parses back."""
    parts = [f'Vorherige Frage: "{state.last_message}"']
    ex = state.last_extracted
    if ex.target_label or ex.target_chf is not None:
        label = ex.target_label or "Ziel"
        amount = _format_chf(ex.target_chf) if ex.target_chf is not None else "unbekannter Betrag"
        parts.append(f"Erkanntes Ziel: {label} für {amount}")
    if ex.merchant_hint:
        parts.append(f"Betroffener Posten: {ex.merchant_hint}")
    parts.append(f"Verwendeter Horizont: {state.last_horizon}")
    parts.append(f"Letzter Antwort-Status: {state.last_status}")
    if state.last_facts_summary:
        parts.append(f"Kernzahlen der letzten Antwort: {state.last_facts_summary}")
    return " | ".join(parts)


def _format_chf(amount: float) -> str:
    return f"CHF {amount:,.0f}".replace(",", "'")


_AMOUNT_LIKE_RE = re.compile(r"\d")


def resolve_pending_clarification(
    state: ConversationState | None,
    context_pending_field: str | None,
    message: str,
) -> str | None:
    """Returns the `field` name to route `message` through
    `intent_service.apply_clarification_answer()` for, or `None` if
    `message` should go through fresh `extract_intent()` instead.

    Two ways a message counts as "answering" the pending clarification:
    - the client explicitly says so (`context_pending_field` matches the
      stored field - the normal case: frontend renders buttons, sends the
      field name back with the click), or
    - no explicit confirmation, but the message text is an unambiguous
      match for one of the fixed button options (covers a client that
      doesn't wire up `context.pending_clarification`, or a user typing
      the answer instead of clicking).

    Deliberately conservative otherwise: if the state has a pending
    clarification but the new message doesn't clearly answer it, this
    falls through to fresh extraction rather than risking misreading an
    unrelated new question as an answer to the old one - the stale
    clarification is simply dropped in that case (T7 doesn't carry it
    forward once a fresh extraction happens).
    """
    if state is None or state.pending_clarification is None:
        return None
    clarification = state.pending_clarification

    if context_pending_field == clarification.field:
        return clarification.field

    normalized = message.strip().lower()
    options_lower = {opt.strip().lower() for opt in clarification.options}
    if normalized in options_lower:
        return clarification.field

    if clarification.field == "target_chf" and _AMOUNT_LIKE_RE.search(message):
        return clarification.field

    return None
