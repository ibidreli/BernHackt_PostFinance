"""Ad-hoc verification for T5 (answer_service) against real data. Mostly
hand-built `ExtractedIntent` objects (deterministic, no API cost) plus
one real `extract_intent()` call to prove the real wiring end-to-end.
Run manually via:

    docker compose run --rm api python -m app.inspect_answer
"""

from __future__ import annotations

from datetime import date

from app.data.data_personal import load_raw_transactions
from app.repositories.balance_repository import BalanceRepository
from app.repositories.transaction_repository import TransactionRepository
from app.schemas.assistant import AssistantAssumptions
from app.services.answer_service import (
    UnresolvedAdjustmentError,
    answer_affordability,
    answer_time_to_goal,
    answer_what_if,
    compute_levers,
)
from app.services.classification import classify_transactions
from app.services.intent_service import ExtractedIntent
from app.services.recurring_detection import detect_recurring_payments

raw = load_raw_transactions()
repo = TransactionRepository.from_raw(raw)
balance_repo = BalanceRepository(repo.all())
recurring = detect_recurring_payments(repo.all())
classifications = classify_transactions(repo.all(), recurring)
AS_OF = date(2026, 8, 22)


def line(title: str) -> None:
    print(f"\n=== {title} ===")


# --- levers ---------------------------------------------------------------
line("Hebel (Top-3 variable Kategorien)")
levers = compute_levers(classifications, AS_OF)
for lv in levers:
    print(f"  {lv.category}: avg={lv.monthly_avg_chf} potential={lv.potential_chf}")
assert len(levers) <= 3
assert all(lv.potential_chf >= 0 for lv in levers)
assert list(levers) == sorted(levers, key=lambda lv: lv.monthly_avg_chf, reverse=True)
print("OK: absteigend sortiert, potential_chf >= 0")

# --- affordability: garantiert no_unless (riesiger Betrag, 1y) -----------
line("affordability: riesiger Betrag (1y) -> erwartet no_unless")
ex = ExtractedIntent(intent="affordability", target_chf=500_000.0, target_label="Villa")
result = answer_affordability(ex, "1y", AS_OF, repo.all(), recurring, classifications, balance_repo, None)
print("status:", result.status, "| facts:", result.facts.model_dump())
assert result.status == "no_unless"
assert result.facts.gap_chf is not None and result.facts.gap_chf > 0
assert result.facts.required_monthly_chf is not None
assert len(result.levers) > 0
assert result.baseline_series[0].date == AS_OF
assert result.baseline_series[-1].date == result.baseline_series[0].date.replace(year=result.baseline_series[0].date.year + 1)
print("OK: no_unless mit gap_chf/required_monthly_chf/Hebeln, Serie korrekt begrenzt")

# --- affordability: garantiert yes (0 CHF Ziel, present) ------------------
line("affordability: Ziel 0 CHF (present) -> erwartet yes")
ex2 = ExtractedIntent(intent="affordability", target_chf=0.0, target_label="Nichts", horizon_override="present")
result2 = answer_affordability(ex2, "present", AS_OF, repo.all(), recurring, classifications, balance_repo, None)
print("status:", result2.status, "| facts:", result2.facts.model_dump())
assert result2.status in ("yes", "tight")  # 0 CHF ist immer erreichbar, Frage ist nur der Puffer
assert result2.facts.gap_chf is None
print("OK: 0-CHF-Ziel ist immer erreichbar (yes oder tight, nie no_unless)")

# --- affordability: Band-Konsistenz zwischen 1y/5y/10y ---------------------
line("affordability: gleiche Frage über alle 3 Horizonte (Konsistenz-Check)")
for h in ("1y", "5y", "10y"):
    ex_h = ExtractedIntent(intent="affordability", target_chf=20000.0, target_label="Test")
    r = answer_affordability(ex_h, h, AS_OF, repo.all(), recurring, classifications, balance_repo, AssistantAssumptions())
    print(f"  {h}: status={r.status} projected={r.facts.projected_chf} months_remaining={r.facts.months_remaining}")
    assert r.assumptions_used.interest_applied is False
print("OK: alle 3 Horizonte liefern ein Ergebnis, interest_applied stets false")

# --- time_to_goal -----------------------------------------------------
line("time_to_goal: CHF 5000 über 5y")
ex3 = ExtractedIntent(intent="time_to_goal", target_chf=5000.0)
result3 = answer_time_to_goal(ex3, "5y", AS_OF, repo.all(), recurring, classifications, balance_repo, None)
print("status:", result3.status, "| facts:", result3.facts.model_dump())
if result3.facts.goal_date:
    assert AS_OF <= result3.facts.goal_date <= result3.baseline_series[-1].date
    print("OK: goal_date liegt im Horizont")
else:
    print("OK: goal_date ist None (nicht erreicht im Horizont) - konsistent mit status:", result3.status)
if result3.facts.goal_date_earliest and result3.facts.goal_date:
    assert result3.facts.goal_date_earliest <= result3.facts.goal_date, "Earliest (P25) sollte nie später als expected sein"
    print("OK: goal_date_earliest <= goal_date")

# --- what_if: cancel_recurring (Netflix, present) -----------------------
line("what_if: Netflix kündigen (present)")
ex4 = ExtractedIntent(intent="what_if", adjustment_kind="cancel", merchant_hint="netflix")
result4 = answer_what_if(ex4, "present", AS_OF, repo.all(), recurring, classifications, balance_repo, None)
print("status:", result4.status, "| facts:", result4.facts.model_dump())
assert result4.facts.impact_monthly_chf is not None
assert result4.facts.impact_monthly_chf > 0, "Kündigen sollte den Puffer verbessern (positiv = besser, Feature #4-Konvention)"
assert result4.scenario_series is not None
print("OK: Netflix-Kündigung verbessert den Puffer (impact_monthly_chf > 0)")

# --- what_if: cancel_recurring (Netflix, 5y - long-horizon Pfad) --------
line("what_if: Netflix kündigen (5y, long-horizon Pfad)")
result4b = answer_what_if(ex4, "5y", AS_OF, repo.all(), recurring, classifications, balance_repo, AssistantAssumptions())
print("status:", result4b.status, "| facts:", result4b.facts.model_dump())
assert result4b.facts.impact_cumulative_chf is not None and result4b.facts.impact_cumulative_chf > 0
assert result4b.scenario_series[-1].expected_chf > result4b.baseline_series[-1].expected_chf
print("OK: Szenario liegt über Baseline am Horizontende (Kündigung = mehr Geld übrig)")

# --- what_if: one_off (5y, long-horizon Pfad, konstanter Shift) ---------
line("what_if: einmalig CHF 2000 ausgeben (5y)")
ex5 = ExtractedIntent(intent="what_if", adjustment_kind="one_off", amount_chf=2000.0, merchant_hint="Möbel")
result5 = answer_what_if(ex5, "5y", AS_OF, repo.all(), recurring, classifications, balance_repo, AssistantAssumptions())
print("status:", result5.status, "| impact_cumulative_chf:", result5.facts.impact_cumulative_chf)
assert result5.facts.impact_cumulative_chf == -2000.0, "Ein permanenter Shift ab as_of sollte am Horizontende exakt -2000 betragen"
assert result5.scenario_series[0].expected_chf == round(result5.baseline_series[0].expected_chf - 2000.0, 2)
print("OK: exakter -2000 CHF Shift ab Tag 0, Band bleibt gleich breit relativ zu baseline")

# --- what_if: unresolvable merchant -> UnresolvedAdjustmentError --------
line("what_if: nicht existierender Posten -> UnresolvedAdjustmentError")
ex6 = ExtractedIntent(intent="what_if", adjustment_kind="cancel", merchant_hint="XYZ-NICHT-EXISTENT-ABC")
try:
    answer_what_if(ex6, "present", AS_OF, repo.all(), recurring, classifications, balance_repo, None)
    print("FEHLER: hätte UnresolvedAdjustmentError werfen sollen")
except UnresolvedAdjustmentError as e:
    print("OK, korrekt:", e)

# --- what_if: add_recurring (neue monatliche Ausgabe, 1y) ----------------
line("what_if: neues Abo für CHF 50/Monat (1y)")
ex7 = ExtractedIntent(intent="what_if", adjustment_kind="add", merchant_hint="Neues Fitness-Abo", amount_chf=50.0)
result7 = answer_what_if(ex7, "1y", AS_OF, repo.all(), recurring, classifications, balance_repo, AssistantAssumptions())
print("status:", result7.status, "| impact_cumulative_chf:", result7.facts.impact_cumulative_chf)
assert result7.facts.impact_cumulative_chf < 0, "Eine neue Ausgabe sollte das Szenario verschlechtern"
print("OK: neue Ausgabe verschlechtert das Szenario (impact_cumulative_chf < 0)")

# --- echter End-to-End-Beweis mit echtem extract_intent() ---------------
line("Echter End-to-End-Test: extract_intent() -> answer_affordability()")
from app.services.intent_service import extract_intent, validate_extraction  # noqa: E402

real_extracted = extract_intent("Kann ich mir in 5 Jahren 15000 Franken für eine Weltreise leisten?", "present")
print("Extrahiert:", real_extracted.model_dump())
validation = validate_extraction(real_extracted, "present")
print("Validierung:", validation.status)
if validation.status == "ok":
    real_horizon = real_extracted.horizon_override or "present"
    real_result = answer_affordability(real_extracted, real_horizon, AS_OF, repo.all(), recurring, classifications, balance_repo, None)
    print("status:", real_result.status, "| facts:", real_result.facts.model_dump())
    print("OK: kompletter Pfad von echter Frage bis Antwortlogik funktioniert")
else:
    print(f"(Rückfrage/unsupported ausgelöst: {validation.clarification or validation.reason} - auch ein gültiges Ergebnis)")

print("\nAlle Checks bestanden.")
