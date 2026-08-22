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
    assert duplicates[0].transaction_id == "hit-1"
    assert duplicates[0].transaction_ids == ["hit-1", "hit-2"]


def test_large_payment_reuses_outlier_but_keeps_absolute_floor() -> None:
    small_rare = tx("small", date(2026, 5, 1), -150.00, merchant="SMALL RARE")
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
    assert large_alerts[0].transaction_id == "large"
    assert large_alerts[0].transaction_ids == ["large"]


def test_large_payment_suppresses_stable_monthly_standing_orders() -> None:
    standing_orders = [
        tx("rent-1", date(2026, 1, 25), -820.00, merchant="LASTSCHRIFT"),
        tx("rent-2", date(2026, 2, 25), -806.30, merchant="LASTSCHRIFT"),
        tx("rent-3", date(2026, 3, 25), -806.30, merchant="LASTSCHRIFT"),
        tx("rent-4", date(2026, 4, 24), -787.00, merchant="LASTSCHRIFT"),
    ]
    standing_orders = [
        t.model_copy(update={"text": f"LASTSCHRIFT DAUERAUFTRAG: 90-27071632 RENT {t.id}"})
        for t in standing_orders
    ]
    one_off = tx("one-off", date(2026, 4, 26), -850.00, merchant="VELO SHOP")
    classes = [
        *(Classification(t, "outlier") for t in standing_orders),
        Classification(one_off, "outlier"),
    ]

    large_alerts = by_type(build_alerts([*standing_orders, one_off], classes), "large_payment")

    assert len(large_alerts) == 1
    assert large_alerts[0].transaction_id == "one-off"


def test_category_spike_uses_only_variable_expenses_and_requires_history() -> None:
    historical = [
        tx("jan", date(2026, 1, 5), -100.00),
        tx("feb", date(2026, 2, 5), -100.00),
        tx("mar", date(2026, 3, 5), -100.00),
        tx("apr", date(2026, 4, 5), -100.00),
    ]
    may_variable = tx("may-variable", date(2026, 5, 5), -400.00)
    may_fixed = tx("may-fixed", date(2026, 5, 6), -500.00)
    may_outlier = tx("may-outlier", date(2026, 5, 7), -500.00)
    classes = [
        *(Classification(t, "variable") for t in historical),
        Classification(may_variable, "variable"),
        Classification(may_fixed, "fixed"),
        Classification(may_outlier, "outlier"),
    ]

    spikes = by_type(
        build_alerts([*historical, may_variable, may_fixed, may_outlier], classes),
        "category_spike",
    )

    assert len(spikes) == 1
    assert spikes[0].month == "2026-05"
    assert spikes[0].amount_chf == 400.00
    assert spikes[0].baseline_chf == 100.00
    assert spikes[0].transaction_id == "may-variable"
    assert spikes[0].transaction_ids == ["may-variable"]


def test_category_spike_stays_quiet_with_less_than_three_baseline_months() -> None:
    transactions = [
        tx("jan", date(2026, 1, 5), -100.00),
        tx("feb", date(2026, 2, 5), -100.00),
        tx("mar", date(2026, 3, 5), -100.00),
        tx("apr", date(2026, 4, 5), -400.00),
    ]

    spikes = by_type(build_alerts(transactions, classifications(transactions)), "category_spike")

    assert spikes == []
