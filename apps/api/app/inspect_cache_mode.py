"""Ad-hoc verification for T9 (cache mode + timeout error). Run via:

    docker compose run --rm api python -m app.inspect_cache_mode

Cache-mode tests force `mode="cached"` explicitly and monkeypatch the
OpenAI client to raise if called at all - proves zero LLM calls happen,
not just that the code *looks* like it skips them.
"""

from __future__ import annotations

from datetime import date
from unittest.mock import patch

from app.data.data_personal import load_raw_transactions
from app.repositories.balance_repository import BalanceRepository
from app.repositories.transaction_repository import TransactionRepository
from app.schemas.assistant import AssistantAskRequest
from app.services.assistant_service import ask
from app.services.cache_service import CACHED_QUESTIONS
from app.services.classification import classify_transactions
from app.services.conversation_state import ConversationStore
from app.services.recurring_detection import detect_recurring_payments

raw = load_raw_transactions()
repo = TransactionRepository.from_raw(raw)
balance_repo = BalanceRepository(repo.all())
recurring = detect_recurring_payments(repo.all())
classifications = classify_transactions(repo.all(), recurring)


def _forbidden_call(*args, **kwargs):
    raise AssertionError("LLM wurde im cached-Modus aufgerufen - das darf nicht passieren!")


def line(title: str) -> None:
    print(f"\n=== {title} ===")


# --- Alle 5 Demo-Fragen, mit garantiert keinem LLM-Call ------------------
line("Alle 5 Cache-Fragen, OpenAI-Client komplett blockiert (AssertionError bei jedem Call-Versuch)")
with patch("app.services.llm_client.get_client", side_effect=_forbidden_call):
    for q in CACHED_QUESTIONS:
        store = ConversationStore()
        req = AssistantAskRequest(message=q.text, horizon="present")
        resp = ask(req, repo.all(), recurring, classifications, balance_repo, store, as_of=date(2026, 8, 22), mode="cached")
        print(f"\n'{q.text}'")
        print(f"  status={resp.status} source={resp.source} intent={resp.intent}")
        print(f"  answer: {resp.answer}")
        assert resp.source == "cached"
        if resp.facts:
            print(f"  facts: {resp.facts.model_dump(exclude_none=True)}")
print("\nOK: alle 5 Demo-Fragen beantwortet, garantiert ohne einen einzigen echten LLM-Call")

# --- Rückfrage-Flow funktioniert auch im cached-Modus (kein LLM nötig) --
line("Rückfrage-Flow im cached-Modus (Auto-Frage -> Bar-Antwort)")
with patch("app.services.llm_client.get_client", side_effect=_forbidden_call):
    store = ConversationStore()
    req1 = AssistantAskRequest(message="Kann ich mir in 5 Jahren ein Auto für 30000 leisten?", horizon="present", context={"conversation_id": "cached-conv"})
    r1 = ask(req1, repo.all(), recurring, classifications, balance_repo, store, as_of=date(2026, 8, 22), mode="cached")
    print(f"1. status={r1.status} | {r1.answer}")
    assert r1.status == "needs_clarification"

    req2 = AssistantAskRequest(message="Bar", horizon="present", context={"conversation_id": "cached-conv", "pending_clarification": "payment_type"})
    r2 = ask(req2, repo.all(), recurring, classifications, balance_repo, store, as_of=date(2026, 8, 22), mode="cached")
    print(f"2. status={r2.status} | {r2.answer}")
    assert r2.status in ("yes", "tight", "no_unless")
    assert r2.source == "cached"
print("OK: Rückfrage-Flow funktioniert vollständig ohne LLM-Call, auch im cached-Modus")

# --- Unbekannte Frage im cached-Modus -> unsupported mit Liste der Demo-Fragen ---
line("Unbekannte Frage im cached-Modus")
with patch("app.services.llm_client.get_client", side_effect=_forbidden_call):
    store = ConversationStore()
    req = AssistantAskRequest(message="Was ist die Hauptstadt von Peru?", horizon="present")
    resp = ask(req, repo.all(), recurring, classifications, balance_repo, store, as_of=date(2026, 8, 22), mode="cached")
    print(f"status={resp.status} | {resp.answer}")
    assert resp.status == "unsupported"
    assert "Kann ich mir in 5 Jahren ein Auto" in resp.answer
print("OK: unbekannte Frage im cached-Modus listet die verfügbaren Demo-Fragen")

# --- Timeout-Stage-Verifikation (live-Modus, echter Fehlerpfad) --------
line("Timeout-Stage: Extraktion vs. Formulierung unterscheidbar")
from app.services.intent_service import extract_intent  # noqa: E402
from app.services.formulation_service import FormulationInput, formulate_answer  # noqa: E402
from app.services.llm_client import AssistantLLMTimeoutError  # noqa: E402
from app.schemas.assistant import AssistantFacts, AssumptionsUsed  # noqa: E402
import os  # noqa: E402

os.environ["ASSISTANT_LLM_TIMEOUT_SECONDS"] = "0.01"
import importlib  # noqa: E402
import app.core.config as config_module  # noqa: E402
importlib.reload(config_module)
import app.services.intent_service as intent_service_module  # noqa: E402
import app.services.formulation_service as formulation_service_module  # noqa: E402
importlib.reload(intent_service_module)
importlib.reload(formulation_service_module)

try:
    intent_service_module.extract_intent("Kann ich mir ein Auto leisten?", "present")
    print("FEHLER: hätte timeouten sollen")
except AssistantLLMTimeoutError as e:
    print(f"Extraktion-Timeout: stage={e.stage!r}")
    assert e.stage == "Extraktion"

try:
    formulation_service_module.formulate_answer(
        formulation_service_module.FormulationInput(
            intent="affordability", status="yes", horizon="1y",
            facts=AssistantFacts(), levers=[],
            assumptions_used=AssumptionsUsed(salary_growth_pct=1.0, inflation_pct=1.5, savings_rate_pct=10.0),
        )
    )
    print("FEHLER: hätte timeouten sollen")
except AssistantLLMTimeoutError as e:
    print(f"Formulierung-Timeout: stage={e.stage!r}")
    assert e.stage == "Formulierung"

print("OK: Timeout-Fehler benennen korrekt, welcher der beiden LLM-Calls betroffen war")

print("\nAlle Checks bestanden.")
