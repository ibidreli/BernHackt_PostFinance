"""Manual inspection tool for recurring-payment detection (T3).

Not an automated test suite - a repeatable way to eyeball grouping,
interval detection, and the salary-day heuristic against the real
dataset. See `app/inspect_transactions.py` for the T1 equivalent.

Run inside the container:
    docker compose run --rm api python -m app.inspect_recurring

Or locally (from apps/api, with the venv active):
    CSV_PATH=../../data/data_personal.csv python -m app.inspect_recurring
"""

from __future__ import annotations

from collections import Counter

from app.data.data_personal import load_raw_transactions
from app.repositories.transaction_repository import TransactionRepository
from app.services.recurring_detection import detect_recurring_payments, detect_salary_day


def main() -> None:
    repo = TransactionRepository.from_raw(load_raw_transactions())
    recurring_payments = detect_recurring_payments(repo.all())

    print(f"recurring payments detected: {len(recurring_payments)}")
    print(f"interval breakdown: {dict(Counter(rp.interval for rp in recurring_payments))}")
    print(f"active: {sum(1 for rp in recurring_payments if rp.is_active)}")
    print(f"salary day: {detect_salary_day(recurring_payments)}")

    print("\nactive recurring payments, largest amount first:")
    active = sorted(
        (rp for rp in recurring_payments if rp.is_active),
        key=lambda rp: -rp.amount_chf,
    )
    for rp in active:
        print(
            f"  {rp.amount_chf:>8.2f}  {rp.flow:<8} {rp.interval:<10} "
            f"day={rp.day_of_month!s:<4} {rp.merchant} "
            f"({rp.category_main}/{rp.category_sub})"
        )


if __name__ == "__main__":
    main()
