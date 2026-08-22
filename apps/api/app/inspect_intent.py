"""Ad-hoc verification for T3 (intent_service) - real OpenAI calls
against the configured OPENAI_MODEL. Run manually via:

    docker compose run --rm api python -m app.inspect_intent
"""

from __future__ import annotations

from app.services.intent_service import (
    apply_clarification_answer,
    extract_intent,
    validate_extraction,
)

CASES: list[tuple[str, str]] = [
    ("Kann ich mir in 5 Jahren ein Auto für 30000 leisten?", "present"),
    ("Wann habe ich 20000 zusammen?", "present"),
    ("Was wäre, wenn ich Netflix kündige?", "1y"),
    ("Was wäre, wenn ich beim Essen die Hälfte spare?", "1y"),  # Kantine-halbieren-Fall -> unsupported
    ("Was ist die beste Aktie gerade?", "present"),  # klar unsupported
    ("Kann ich mir ein Auto leisten?", "5y"),  # kein Betrag -> Rückfrage target_chf
    ("Kann ich mir in 5 Jahren einen Töff für 12000 leisten?", "present"),  # grosse Anschaffung, kein payment_type -> Rückfrage
    ("Was wäre, wenn ich monatlich 50 mehr für Möbel ausgebe?", "1y"),  # adjustment_kind ambig? sollte "add" liefern
]

for message, horizon in CASES:
    print(f"\n=== Frage: {message!r} (horizon={horizon}) ===")
    extracted = extract_intent(message, horizon)
    print("Extrahiert:", extracted.model_dump())
    result = validate_extraction(extracted, horizon)
    print("Validierung:", result.status, "|", result.clarification.model_dump() if result.clarification else result.reason)

print("\n\n=== Clarification-Answer-Test (deterministisch, kein LLM-Call) ===")
base = extract_intent("Kann ich mir in 5 Jahren einen Töff für 12000 leisten?", "present")
print("Vor Antwort:", base.model_dump())

answer = apply_clarification_answer(base, "payment_type", "Leasing")
print("Nach 'Leasing' (Button):", answer.extracted.payment_type, "| default_used:", answer.default_used)
assert answer.extracted.payment_type == "leasing" and answer.default_used is None

answer2 = apply_clarification_answer(base, "payment_type", "hmpf keine Ahnung")
print("Nach Freitext-Antwort (kein Button-Match):", answer2.extracted.payment_type, "| default_used:", answer2.default_used)
assert answer2.extracted.payment_type == "cash" and answer2.default_used == "Bar"

amount_case = extract_intent("Kann ich mir ein Auto leisten?", "5y")
answer3 = apply_clarification_answer(amount_case, "target_chf", "CHF 30'000.-")
print("Nach Betrags-Freitext \"CHF 30'000.-\":", answer3.extracted.target_chf)
assert answer3.extracted.target_chf == 30000.0

print("\nAlle Checks bestanden.")
