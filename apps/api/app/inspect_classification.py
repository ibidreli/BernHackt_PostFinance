"""Manual inspection tool for the Drei-Topf-Klassifikation (T4).

Not an automated test suite - a repeatable way to eyeball topf
assignment and the outlier threshold against the real dataset. See
`app/inspect_transactions.py` (T1) and `app/inspect_recurring.py` (T3)
for the equivalents on the earlier steps.

Run inside the container:
    docker compose run --rm api python -m app.inspect_classification

Or locally (from apps/api, with the venv active):
    CSV_PATH=../../data/data_personal.csv python -m app.inspect_classification
"""

from __future__ import annotations

from collections import Counter

from app.data.data_personal import load_raw_transactions
from app.repositories.transaction_repository import TransactionRepository
from app.services.classification import classify_transactions
from app.services.recurring_detection import detect_recurring_payments


def main() -> None:
    repo = TransactionRepository.from_raw(load_raw_transactions())
    transactions = repo.all()
    recurring_payments = detect_recurring_payments(transactions)
    classifications = classify_transactions(transactions, recurring_payments)

    print(f"topf breakdown: {dict(Counter(c.topf for c in classifications))}")

    fixed_merchants = sorted(
        {c.recurring_payment.merchant for c in classifications if c.topf == "fixed"}
    )
    print(f"\ndistinct Topf-1 (fixed) merchants: {len(fixed_merchants)}")
    for m in fixed_merchants:
        print(f"  {m}")

    outliers = [c for c in classifications if c.topf == "outlier"]
    print(f"\nTopf-3 (outlier) category breakdown ({len(outliers)} total):")
    for cat, n in Counter(
        (c.transaction.category_main, c.transaction.category_sub) for c in outliers
    ).most_common(15):
        print(f"  {n:>4}  {cat}")

    print("\nlargest outliers (sanity check - should look like Reisen/Velokauf/Steuern-style one-offs):")
    for c in sorted(outliers, key=lambda c: -abs(c.transaction.amount_chf))[:10]:
        t = c.transaction
        print(f"  {t.date} {t.amount_chf:>10.2f}  {t.category_main}/{t.category_sub}  {t.merchant}")


if __name__ == "__main__":
    main()
