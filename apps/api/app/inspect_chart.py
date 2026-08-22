"""Ad-hoc verification for T6 (chart_service) against real data. Run via:

    docker compose run --rm api python -m app.inspect_chart
"""

from __future__ import annotations

from datetime import date

from app.data.data_personal import load_raw_transactions
from app.repositories.balance_repository import BalanceRepository
from app.repositories.transaction_repository import TransactionRepository
from app.schemas.assistant import AssistantAssumptions
from app.services.answer_service import answer_affordability, answer_time_to_goal, answer_what_if
from app.services.chart_service import build_chart
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


# --- affordability -> wealth_over_time -------------------------------
line("affordability (no_unless, 1y) -> wealth_over_time")
ex = ExtractedIntent(intent="affordability", target_chf=500_000.0, target_label="Villa")
result = answer_affordability(ex, "1y", AS_OF, repo.all(), recurring, classifications, balance_repo, None)
chart = build_chart("affordability", result)
print("type:", chart.type, "| target_line_chf:", chart.target_line_chf, "| crossing_date:", chart.crossing_date, "| n_points:", len(chart.series))
assert chart.type == "wealth_over_time"
assert chart.target_line_chf == result.facts.target_chf
assert chart.crossing_date is None, "500'000 wird nie erreicht -> keine Kreuzung"
assert chart.series[-1].expected_chf == result.facts.projected_chf, "Chart-Endpunkt muss exakt facts.projected_chf entsprechen"
assert chart.series[0].date == AS_OF and chart.series[0].lower_chf == chart.series[0].upper_chf == chart.series[0].expected_chf
print("OK: target_line/crossing/Serie konsistent mit facts, Band bei Tag 0 exakt 0 breit")

line("affordability (yes, kleines Ziel, 1y) -> Kreuzung MUSS existieren")
ex2 = ExtractedIntent(intent="affordability", target_chf=1000.0, target_label="Velo")
result2 = answer_affordability(ex2, "1y", AS_OF, repo.all(), recurring, classifications, balance_repo, AssistantAssumptions())
chart2 = build_chart("affordability", result2)
print("status:", result2.status, "| crossing_date:", chart2.crossing_date)
assert result2.status in ("yes", "tight")
assert chart2.crossing_date is not None, "Ziel erreicht -> Kreuzung muss existieren"
assert AS_OF <= chart2.crossing_date <= chart2.series[-1].date
print("OK: Kreuzung existiert und liegt im Horizont")

# --- time_to_goal -> goal_progress ------------------------------------
line("time_to_goal -> goal_progress")
ex3 = ExtractedIntent(intent="time_to_goal", target_chf=5000.0)
result3 = answer_time_to_goal(ex3, "5y", AS_OF, repo.all(), recurring, classifications, balance_repo, None)
chart3 = build_chart("time_to_goal", result3)
print("type:", chart3.type, "| target_chf:", chart3.target_chf, "| expected_date:", chart3.expected_date, "| earliest:", chart3.earliest_date, "| latest:", chart3.latest_date)
assert chart3.type == "goal_progress"
assert chart3.target_chf == result3.facts.target_chf
assert chart3.expected_date == result3.facts.goal_date
assert chart3.earliest_date == result3.facts.goal_date_earliest
assert chart3.latest_date == result3.facts.goal_date_latest
print("OK: goal_progress-Felder exakt aus facts übernommen")

# --- what_if -> before_after -------------------------------------------
line("what_if: Netflix kündigen (5y) -> before_after")
ex4 = ExtractedIntent(intent="what_if", adjustment_kind="cancel", merchant_hint="netflix")
result4 = answer_what_if(ex4, "5y", AS_OF, repo.all(), recurring, classifications, balance_repo, AssistantAssumptions())
chart4 = build_chart("what_if", result4)
print("type:", chart4.type, "| diff_at_horizon_chf:", chart4.diff_at_horizon_chf, "| facts.impact_cumulative_chf:", result4.facts.impact_cumulative_chf)
assert chart4.type == "before_after"
assert chart4.diff_at_horizon_chf == result4.facts.impact_cumulative_chf, "Chart-Diff muss exakt facts.impact_cumulative_chf entsprechen"
assert len(chart4.baseline_series) == len(chart4.scenario_series)
assert chart4.baseline_series[0].date == chart4.scenario_series[0].date == AS_OF
print("OK: diff_at_horizon_chf konsistent mit facts, beide Serien gleich lang und beginnen bei as_of")

line("what_if: no_unless-Status bekommt trotzdem before_after (nicht wealth_over_time)")
ex5 = ExtractedIntent(intent="what_if", adjustment_kind="add", merchant_hint="Sehr teures neues Abo", amount_chf=5000.0)
result5 = answer_what_if(ex5, "1y", AS_OF, repo.all(), recurring, classifications, balance_repo, AssistantAssumptions())
chart5 = build_chart("what_if", result5)
print("status:", result5.status, "| chart type:", chart5.type)
assert result5.status == "no_unless", "CHF 5000/Monat zusätzlich sollte garantiert ins Minus treiben"
assert chart5.type == "before_after", "what_if bleibt IMMER before_after, auch bei no_unless"
print("OK: Chart-Typ hängt nur vom Intent ab, nicht vom Status")

print("\nAlle Checks bestanden.")
