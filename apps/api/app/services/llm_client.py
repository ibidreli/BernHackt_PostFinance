"""Shared OpenAI client + error types for both LLM calls in the issue's
architecture diagram - extraction (T3) and formulation (T7/T10). One
place so a timeout or API failure always becomes the same explicit
exception in both calls, never a silent fallback that pretends to have
worked (your instruction, see ASSISTANT_STATUS.md T9).

Split out of `intent_service.py` once formulation (T7) needed the exact
same client/error handling - avoided duplicating it a second time.
"""

from __future__ import annotations

from openai import OpenAI

from app.core.config import OPENAI_API_KEY

_client: OpenAI | None = None


def get_client() -> OpenAI:
    global _client
    if _client is None:
        _client = OpenAI(api_key=OPENAI_API_KEY)
    return _client


class AssistantLLMError(Exception):
    """Base class for any LLM-call failure in this feature (extraction
    in T3, formulation in T7/T10). The API layer (T11) turns this into
    an explicit error response for the user - never a silent fallback."""


class AssistantLLMTimeoutError(AssistantLLMError):
    """`stage` names which of the two LLM calls timed out ("Extraktion"
    or "Formulierung", set by the respective call sites) - T9 addition,
    so the eventual HTTP error (T11) can be specific instead of a bare
    "something timed out"."""

    def __init__(self, seconds: float, stage: str = "LLM-Call"):
        self.seconds = seconds
        self.stage = stage
        super().__init__(f"{stage} hat das Timeout von {seconds}s überschritten.")
