from __future__ import annotations

from datetime import date

from app.models.transaction import Transaction
from app.services.alert_service import build_alerts
from app.services.classification import Classification


def tx(
    id_: str,
    day: date,
    amount: float,
    *,
    merchant: str = "MIGROS",
    category_main: str = "Einkaufen",
    category_sub: str = "Supermaerkte",
    flow: str = "expense",
    is_transfer: bool = False,
) -> Transaction:
    return Transaction(
        id=id_,
        date=day,
        value_date=day,
        text=f"{merchant} booking {id_}",
        merchant=merchant,
        merchant_canonical=merchant.lower(),
        bank_label=None,
        category_main=category_main,
        category_sub=category_sub,
        amount_chf=amount,
        flow=flow,
        balance_chf=0.0,
        is_transfer=is_transfer,
    )


def classifications(transactions: list[Transaction], topf: str = "variable") -> list[Classification]:
    return [Classification(t, topf) for t in transactions]  # type: ignore[arg-type]


def by_type(alerts, type_: str):
    return [a for a in alerts if a.type == type_]


def test_duplicate_charge_needs_floor_and_ignores_transfers() -> None:
    transactions = [
        tx("low-1", date(2026, 3, 14), -19.95),
        tx("low-2", date(2026, 3, 14), -19.95),
        tx("transfer-1", date(2026, 3, 15), -120.00, is_transfer=True),
        tx("transfer-2", date(2026, 3, 15), -120.00, is_transfer=True),
        tx("hit-1", date(2026, 3, 16), -45.90),
        tx("hit-2", date(2026, 3, 16), -45.90),
    ]

    duplicates = by_type(build_alerts(transactions, classifications(transactions)), "duplicate_charge")

    assert len(duplicates) == 1
    assert duplicates[0].amount_chf == 45.90
    assert duplicates[0].count == 2


def test_large_payment_reuses_outlier_but_keeps_absolute_floor() -> None:
    small_rare = tx("small", date(2026, 5, 1), -80.00, merchant="SMALL RARE")
    real_large = tx("large", date(2026, 5, 2), -450.00, merchant="VELO SHOP")
    income_outlier = tx("income", date(2026, 5, 3), 1000.00, merchant="EMPLOYER", flow="income")
    classes = [
        Classification(small_rare, "outlier"),
        Classification(real_large, "outlier"),
        Classification(income_outlier, "outlier"),
    ]

    large_alerts = by_type(build_alerts([small_rare, real_large, income_outlier], classes), "large_payment")

    assert len(large_alerts) == 1
    assert large_alerts[0].merchant == "VELO SHOP"
    assert large_alerts[0].amount_chf == 450.00


def test_category_spike_uses_only_variable_expenses_and_requires_history() -> None:
    historical = [
        tx("jan", date(2026, 1, 5), -100.00),
        tx("feb", date(2026, 2, 5), -100.00),
        tx("mar", date(2026, 3, 5), -100.00),
    ]
    april_variable = tx("apr-variable", date(2026, 4, 5), -300.00)
    april_fixed = tx("apr-fixed", date(2026, 4, 6), -500.00)
    april_outlier = tx("apr-outlier", date(2026, 4, 7), -500.00)
    classes = [
        *(Classification(t, "variable") for t in historical),
        Classification(april_variable, "variable"),
        Classification(april_fixed, "fixed"),
        Classification(april_outlier, "outlier"),
    ]

    spikes = by_type(
        build_alerts([*historical, april_variable, april_fixed, april_outlier], classes),
        "category_spike",
    )

    assert len(spikes) == 1
    assert spikes[0].month == "2026-04"
    assert spikes[0].amount_chf == 300.00
    assert spikes[0].baseline_chf == 100.00


def test_category_spike_stays_quiet_with_less_than_three_baseline_months() -> None:
    transactions = [
        tx("jan", date(2026, 1, 5), -100.00),
        tx("feb", date(2026, 2, 5), -100.00),
        tx("mar", date(2026, 3, 5), -300.00),
    ]

    spikes = by_type(build_alerts(transactions, classifications(transactions)), "category_spike")

    assert spikes == []
