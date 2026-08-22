"""Ad-hoc verification for T4 (conversation_state) - uses real
`extract_intent()` calls (T3) to build realistic `ExtractedIntent`
objects, then exercises the store/summary/resolve mechanics without
needing T5-T7 (which don't exist yet). Run manually via:

    docker compose run --rm api python -m app.inspect_conversation_state
"""

from __future__ import annotations

from app.schemas.assistant import Clarification
from app.services.conversation_state import (
    ConversationState,
    ConversationStore,
    build_prior_turn_summary,
    resolve_pending_clarification,
)
from app.services.intent_service import extract_intent

store = ConversationStore()

print("=== Store: leer, unbekannte conversation_id ===")
assert store.get("nicht-vorhanden") is None
assert len(store) == 0
print("OK\n")

print("=== Turn 1: echte Extraktion, State speichern ===")
extracted = extract_intent("Kann ich mir in 5 Jahren ein Auto für 30000 leisten?", "present")
print("Extrahiert:", extracted.model_dump())

state = ConversationState(
    conversation_id="conv-1",
    last_message="Kann ich mir in 5 Jahren ein Auto für 30000 leisten?",
    last_extracted=extracted,
    last_horizon="5y",
    last_intent="affordability",
    last_status="no_unless",
    last_facts_summary="Fehlbetrag CHF 7'400, nötig CHF 125/Monat mehr",
    pending_clarification=None,
)
store.save(state)
assert len(store) == 1
fetched = store.get("conv-1")
assert fetched is not None and fetched.last_message == state.last_message
print("OK: gespeichert und wieder gefunden\n")

print("=== Folgefrage-Zusammenfassung ===")
summary = build_prior_turn_summary(state)
print(summary)
assert "Auto" in summary and "30'000" in summary and "5y" in summary and "no_unless" in summary
print("OK: enthält Ziel, Betrag, Horizont, Status\n")

print("=== Folgefrage tatsächlich an die echte Extraktion geben ===")
followup = extract_intent("Und wenn ich 2 Jahre länger warte?", "5y", prior_turn_summary=summary)
print("Extrahiert (mit Kontext):", followup.model_dump())
assert followup.target_chf == 30000.0, "Sollte den Betrag aus dem Kontext übernommen haben"
assert followup.horizon_override == "10y" or followup.horizon_override is None, (
    "Erwartet: entweder erkennt es '2 Jahre länger' als 10y (5+2 näher an 10y als 5y), oder lässt es offen"
)
print("OK: Ziel-Betrag aus Kontext übernommen, horizon_override:", followup.horizon_override)

print("\n=== Rückfrage-Zustand: pending_clarification setzen ===")
clar = Clarification(question="Bar oder Leasing?", options=["Bar", "Leasing"], field="payment_type")
state2 = ConversationState(
    conversation_id="conv-2",
    last_message="Kann ich mir in 5 Jahren einen Töff für 12000 leisten?",
    last_extracted=extract_intent("Kann ich mir in 5 Jahren einen Töff für 12000 leisten?", "present"),
    last_horizon="5y",
    last_intent="affordability",
    last_status="needs_clarification",
    last_facts_summary=None,
    pending_clarification=clar,
)
store.save(state2)

print("--- Fall A: Client bestätigt explizit über context.pending_clarification ---")
field = resolve_pending_clarification(state2, "payment_type", "Leasing")
assert field == "payment_type"
print("OK:", field)

print("--- Fall B: Kein expliziter Kontext, aber Text matched einen Button ---")
field_b = resolve_pending_clarification(state2, None, "Bar")
assert field_b == "payment_type"
print("OK:", field_b)

print("--- Fall C: Kein Match, klar eine neue Frage -> fresh extraction ---")
field_c = resolve_pending_clarification(state2, None, "Wie viel Geld habe ich gerade?")
assert field_c is None
print("OK: korrekt None (neue Frage, keine Rückfrage-Antwort)")

print("--- Fall D: Keine pending_clarification im State -> immer None ---")
field_d = resolve_pending_clarification(state, None, "Leasing")
assert field_d is None
print("OK: korrekt None (state hat keine offene Rückfrage)")

print("\nAlle Checks bestanden.")
