"""Ad-hoc verification for T2 (`project_long_term`) against the real
sample data - not an automated test (explicit project decision, see
STATUS_FEATURE_NR_4_BACKEND.md), run manually via:

    docker compose run --rm api python -m app.inspect_longterm
"""

from __future__ import annotations

from app.data.data_personal import load_raw_transactions
from app.repositories.balance_repository import BalanceRepository
from app.repositories.transaction_repository import TransactionRepository
from app.services.classification import classify_transactions
from app.services.forecast_service import LONG_HORIZON_MONTHS, project_long_term
from app.services.recurring_detection import detect_recurring_payments

raw = load_raw_transactions()
repo = TransactionRepository.from_raw(raw)
balance_repo = BalanceRepository(repo.all())
recurring = detect_recurring_payments(repo.all())
classifications = classify_transactions(repo.all(), recurring)

print("=== T2: project_long_term Sanity-Checks ===\n")

for horizon, months in LONG_HORIZON_MONTHS.items():
    result = project_long_term(repo.all(), recurring, classifications, balance_repo, months=months)
    first, last = result.series[0], result.series[-1]
    print(f"--- {horizon} ({months} Monate) ---")
    print(f"as_of={result.as_of} horizon_end={result.horizon_end} opening={result.opening_balance_chf}")
    print(
        f"monthly_income={result.monthly_income_chf} monthly_fixed={result.monthly_fixed_expense_chf} "
        f"monthly_variable={result.monthly_variable_expense_chf} savings_rate_pct={result.savings_rate_pct}"
    )
    print(f"growth={result.salary_growth_pct}% inflation={result.inflation_pct}% months_used={result.variable_baseline_months_used}")
    print(f"series points: {len(result.series)} (erwartet {months + 1})")
    print(f"Punkt m=0: {first} <- Band muss exakt 0 breit sein")
    assert first.lower_chf == first.expected_chf == first.upper_chf, "Band bei m=0 nicht 0 breit!"
    print(f"Punkt m={months}: {last}")
    print(f"excluded_outliers: {result.excluded_outliers}")
    print(f"notes: {result.notes}")
    print()

print("=== Savings-rate-Override-Check (50% erzwungen) ===")
r = project_long_term(repo.all(), recurring, classifications, balance_repo, months=60, savings_rate_pct=50.0)
print(f"savings_rate_pct (sollte exakt 50.0 sein): {r.savings_rate_pct}")
assert r.savings_rate_pct == 50.0
expected_60 = r.opening_balance_chf + 0.5 * sum(r.monthly_income_chf * (1.0 ** i) for i in range(60))
print(f"expected_chf bei m=60 (grobe Kontrolle ohne Wachstum): {r.series[-1].expected_chf}")

print("\n=== Wachstum-Sanity: 5y mit 0% vs. 5% Lohnwachstum, gleiche Inflation ===")
low = project_long_term(repo.all(), recurring, classifications, balance_repo, months=60, salary_growth_pct=0.0, inflation_pct=0.0)
high = project_long_term(repo.all(), recurring, classifications, balance_repo, months=60, salary_growth_pct=5.0, inflation_pct=0.0)
print(f"0% Wachstum -> expected_chf @60m: {low.series[-1].expected_chf}")
print(f"5% Wachstum -> expected_chf @60m: {high.series[-1].expected_chf}")
assert high.series[-1].expected_chf > low.series[-1].expected_chf, "Mehr Lohnwachstum sollte mehr Endvermögen bedeuten!"
print("OK: mehr Lohnwachstum -> mehr Endvermögen, wie erwartet.\n")

print("=== Inflation-Sanity: 5y mit 0% vs. 5% Inflation, gleiches Wachstum ===")
low_i = project_long_term(repo.all(), recurring, classifications, balance_repo, months=60, salary_growth_pct=0.0, inflation_pct=0.0)
high_i = project_long_term(repo.all(), recurring, classifications, balance_repo, months=60, salary_growth_pct=0.0, inflation_pct=5.0)
print(f"0% Inflation -> expected_chf @60m: {low_i.series[-1].expected_chf}")
print(f"5% Inflation -> expected_chf @60m: {high_i.series[-1].expected_chf}")
assert high_i.series[-1].expected_chf < low_i.series[-1].expected_chf, "Mehr Inflation sollte weniger Endvermögen bedeuten!"
print("OK: mehr Inflation -> weniger Endvermögen, wie erwartet.\n")

print("=== Fixkosten bleiben nominal flach (Team-Entscheidung) ===")
# monthly_fixed_expense_chf sollte unabhängig von inflation_pct gleich sein,
# da Fixkosten laut Entscheidung nicht mit inflation_pct wachsen.
r_low = project_long_term(repo.all(), recurring, classifications, balance_repo, months=12, inflation_pct=0.0)
r_high = project_long_term(repo.all(), recurring, classifications, balance_repo, months=12, inflation_pct=5.0)
print(f"monthly_fixed_expense_chf bei 0% Inflation: {r_low.monthly_fixed_expense_chf}")
print(f"monthly_fixed_expense_chf bei 5% Inflation: {r_high.monthly_fixed_expense_chf}")
assert r_low.monthly_fixed_expense_chf == r_high.monthly_fixed_expense_chf
print("OK: monthly_fixed_expense_chf identisch, wie erwartet.\n")

print("Alle Checks bestanden.")
