"""Manual inspection tool for the forecast service (T7).

Not an automated test suite - a repeatable way to eyeball forecast() and
simulate() output against the real dataset. See app/inspect_*.py for the
equivalents on earlier steps.

Run inside the container:
    docker compose run --rm api python -m app.inspect_forecast

Or locally (from apps/api, with the venv active):
    CSV_PATH=../../data/data_personal.csv python -m app.inspect_forecast
"""

from __future__ import annotations

from datetime import date

from app.data.data_personal import load_raw_transactions
from app.repositories.balance_repository import BalanceRepository
from app.repositories.transaction_repository import TransactionRepository
from app.schemas.forecast import CancelRecurring
from app.services.classification import classify_transactions
from app.services.forecast_service import forecast, simulate
from app.services.recurring_detection import (
    detect_recurring_payments,
    detect_salary_recurring,
    recurring_payment_id,
)


def main() -> None:
    repo = TransactionRepository.from_raw(load_raw_transactions())
    transactions = repo.all()
    recurring_payments = detect_recurring_payments(transactions)
    classifications = classify_transactions(transactions, recurring_payments)
    balance_repo = BalanceRepository(transactions)

    as_of = date.today()
    print(f"as_of: {as_of}\n")

    for horizon in ("next_salary", "30d", "90d", "365d"):
        f = forecast(transactions, recurring_payments, classifications, balance_repo, horizon=horizon, as_of=as_of)
        print(f"=== {horizon} (ends {f.horizon_end}) ===")
        print(f"  opening_balance_chf: {f.opening_balance_chf}")
        print(f"  next_salary: {f.next_salary}")
        print(f"  free_to_spend: {f.free_to_spend}")
        print(f"  tight_date: {f.tight_date}")
        print(f"  known_payments: {len(f.known_payments)}, series points: {len(f.series)}")
        print(f"  assumptions.notes: {f.assumptions.notes}")
        print()

    salary = detect_salary_recurring(recurring_payments)
    netflix = next((rp for rp in recurring_payments if rp.merchant == "NETFLIX.COM"), None)
    if netflix:
        print("=== simulate(): Preset 'Netflix kündigen', horizon=365d ===")
        res = simulate(
            transactions,
            recurring_payments,
            classifications,
            balance_repo,
            [CancelRecurring(recurring_id=recurring_payment_id(netflix))],
            horizon="365d",
            as_of=as_of,
        )
        print(f"  diff.monthly_chf: {res.diff.monthly_chf}")
        print(f"  diff.total_at_horizon_chf: {res.diff.total_at_horizon_chf}")
        print(f"  diff.tight_date_shift_days: {res.diff.tight_date_shift_days}")


if __name__ == "__main__":
    main()
