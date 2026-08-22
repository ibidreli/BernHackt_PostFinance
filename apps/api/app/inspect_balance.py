"""Manual inspection tool for the balance reconstruction (T6) and the
monthly category stats (T5).

Not an automated test suite - a repeatable way to verify the balance
reconstruction against real recorded checkpoints and eyeball the
category-level P25/median/P75 baseline. See `app/inspect_transactions.py`
(T1), `app/inspect_recurring.py` (T3), `app/inspect_classification.py`
(T4) for the equivalents on earlier steps.

Run inside the container:
    docker compose run --rm api python -m app.inspect_balance

Or locally (from apps/api, with the venv active):
    CSV_PATH=../../data/data_personal.csv python -m app.inspect_balance
"""

from __future__ import annotations

import math
from collections import defaultdict

from app.data.data_personal import load_raw_transactions
from app.repositories.balance_repository import BalanceRepository
from app.repositories.transaction_repository import TransactionRepository, monthly_category_stats
from app.services.classification import classify_transactions
from app.services.recurring_detection import detect_recurring_payments


def main() -> None:
    repo = TransactionRepository.from_raw(load_raw_transactions())
    transactions = repo.all()
    bal_repo = BalanceRepository(transactions)

    # T6: verify day-level reconstruction against every calendar day that
    # has a genuinely recorded balance (the granularity `as_of(date)`
    # actually promises - see module docstring in balance_repository.py).
    by_date = defaultdict(list)
    for t in transactions:
        by_date[t.date].append(t)

    checked, mismatches = 0, 0
    for d, day_txs in sorted(by_date.items()):
        last_of_day = day_txs[-1]
        if math.isnan(last_of_day.balance_chf):
            continue
        checked += 1
        recon = bal_repo.as_of(d)
        if recon is None or abs(recon.balance_chf - last_of_day.balance_chf) > 0.01:
            mismatches += 1
            print(f"  MISMATCH {d}: recorded={last_of_day.balance_chf} reconstructed={recon}")

    print(f"day-level balance checkpoints verified: {checked}, mismatches: {mismatches}")

    latest = bal_repo.latest()
    print(f"latest known balance: {latest}")

    # T5: category baseline as of the latest known date.
    print("\nmonthly category stats (Topf 2 only), as of latest balance date:")
    recurring_payments = detect_recurring_payments(transactions)
    classifications = classify_transactions(transactions, recurring_payments)
    variable_txs = [c.transaction for c in classifications if c.topf == "variable"]
    stats = monthly_category_stats(variable_txs, as_of=latest.as_of) if latest else []
    for s in sorted(stats, key=lambda s: -s.median_chf):
        sub = s.category_sub or "-"
        print(
            f"  {s.category_main}/{sub:<25} p25={s.p25_chf:>8.2f} "
            f"median={s.median_chf:>8.2f} p75={s.p75_chf:>8.2f} months={s.months_used}"
        )


if __name__ == "__main__":
    main()
