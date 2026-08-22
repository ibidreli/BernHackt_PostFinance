"""End-to-end verification for T7 (assistant_service) - the full
architecture diagram, real OpenAI calls throughout. Run via:

    docker compose run --rm api python -m app.inspect_assistant
"""

from __future__ import annotations

from app.data.data_personal import load_raw_transactions
from app.repositories.balance_repository import BalanceRepository
from app.repositories.transaction_repository import TransactionRepository
from app.schemas.assistant import AssistantAskRequest, AssistantContext
from app.services.assistant_service import ask
from app.services.classification import classify_transactions
from app.services.conversation_state import ConversationStore
from app.services.recurring_detection import detect_recurring_payments

raw = load_raw_transactions()
repo = TransactionRepository.from_raw(raw)
balance_repo = BalanceRepository(repo.all())
recurring = detect_recurring_payments(repo.all())
classifications = classify_transactions(repo.all(), recurring)
store = ConversationStore()


def line(title: str) -> None:
    print(f"\n=== {title} ===")


def call(message: str, horizon="present", conversation_id=None, pending_clarification=None):
    req = AssistantAskRequest(
        message=message,
        horizon=horizon,
        context=AssistantContext(conversation_id=conversation_id, pending_clarification=pending_clarification)
        if conversation_id
        else None,
    )
    resp = ask(req, repo.all(), recurring, classifications, balance_repo, store)
    print(f"  intent={resp.intent} status={resp.status} source={resp.source}")
    print(f"  answer: {resp.answer}")
    if resp.facts:
        print(f"  facts: {resp.facts.model_dump(exclude_none=True)}")
    if resp.levers:
        print(f"  levers: {[l.category for l in resp.levers]}")
    if resp.chart:
        print(f"  chart: {resp.chart.type}")
    if resp.clarification:
        print(f"  clarification: {resp.clarification.model_dump()}")
    return resp


# --- 1. what_if, direkte Antwort (kein Rückfrage nötig) -------------------
line("1. what_if: Netflix kündigen, 5y")
r1 = call("Was wäre, wenn ich Netflix kündige?", horizon="5y")
assert r1.status != "unsupported"
assert r1.chart is not None and r1.chart.type == "before_after"
assert r1.assumptions_used is not None and r1.assumptions_used.interest_applied is False
print("OK: what_if direkt beantwortet, before_after-Chart, interest_applied=false")

# --- 2. unsupported: kein LLM-Call #2, fixe Antwort -----------------------
line("2. unsupported: Smalltalk")
r2 = call("Wie ist das Wetter heute?")
assert r2.status == "unsupported" and r2.intent == "unsupported"
assert "drei Dingen" in r2.answer
assert r2.chart is None and r2.facts is None
print("OK: fixe unsupported-Antwort, kein Chart, keine facts")

# --- 3. affordability -> Rückfrage (grosse Anschaffung, present) ---------
line("3. affordability: Auto 30000 in 5 Jahren -> Rückfrage")
r3 = call("Kann ich mir in 5 Jahren ein Auto für 30000 leisten?", conversation_id="conv-auto")
assert r3.status == "needs_clarification"
assert r3.clarification is not None and r3.clarification.field == "payment_type"
print("OK: Rückfrage ausgelöst, State unter 'conv-auto' gespeichert")

# --- 4. Folgefrage beantwortet die Rückfrage über dieselbe conversation_id
line("4. Rückfrage beantworten: 'Bar'")
r4 = call("Bar", conversation_id="conv-auto", pending_clarification="payment_type")
print(f"  status nach Rückfrage-Antwort: {r4.status}")
assert r4.status in ("yes", "tight", "no_unless"), "Nach Beantwortung sollte eine echte Berechnung erfolgen"
assert r4.facts is not None and r4.facts.target_chf == 30000.0
assert r4.chart is not None and r4.chart.type == "wealth_over_time"
print("OK: Rückfrage korrekt aufgelöst, echte Berechnung mit target_chf=30000 aus dem 1. Turn")

# --- 5. Folgefrage OHNE explizite Bestätigung, nur Text-Match -------------
line("5. Neue Rückfrage + Antwort per Text (ohne context.pending_clarification)")
r5a = call("Kann ich mir in 10 Jahren einen Töff für 8000 leisten?", conversation_id="conv-toff")
assert r5a.status == "needs_clarification"
r5b = call("Leasing", conversation_id="conv-toff")  # kein pending_clarification im Request, nur Text-Match
assert r5b.status in ("yes", "tight", "no_unless")
assert r5b.facts.target_chf == 8000.0
print("OK: Rückfrage auch ohne expliziten Feld-Hinweis über Text-Match aufgelöst")

# --- 6. Echte Folgefrage (kein Rückfrage-Kontext, sondern Bezug auf vorherige Antwort) ---
line("6. Echte Folgefrage: 'Und wenn ich 2 Jahre länger warte?'")
r6a = call("Kann ich mir in 5 Jahren ein Auto für 30000 leisten?", conversation_id="conv-followup")
# r6a löst vermutlich eine Rückfrage aus (Bar/Leasing) - beantworten:
if r6a.status == "needs_clarification":
    r6a = call("Bar", conversation_id="conv-followup", pending_clarification=r6a.clarification.field)
print(f"  status nach 1. Antwort: {r6a.status}")
r6b = call("Und wenn ich 2 Jahre länger warte?", conversation_id="conv-followup")
print(f"  status Folgefrage: {r6b.status} | facts: {r6b.facts.model_dump(exclude_none=True) if r6b.facts else None}")
assert r6b.status != "unsupported", "Sollte den Kontext (Ziel=Auto, Betrag=30000) übernehmen können"
assert r6b.facts is not None and r6b.facts.target_chf == 30000.0
print("OK: echte Folgefrage über Conversation-State aufgelöst, Zielbetrag übernommen")

# --- 7. time_to_goal ------------------------------------------------------
line("7. time_to_goal: CHF 10000 in 5 Jahren")
r7 = call("Wann habe ich 10000 zusammen?", horizon="5y")
assert r7.status != "unsupported"
if r7.chart:
    assert r7.chart.type == "goal_progress"
print("OK: time_to_goal -> goal_progress-Chart")

print("\nAlle Checks bestanden.")
