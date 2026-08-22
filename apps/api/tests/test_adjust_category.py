"""`adjust_category` (Sollstatus): scales a Topf-2 category's share of
the variable baseline in `simulate()`. Category names/medians refer to
the committed CSV as of 2026-06-15 (Freizeit ≈ 483/M, sub Gastronomie
≈ 381/M) - same regeneration rule as test_forecast_service.py."""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from app.schemas.forecast import AdjustCategory
from app.services.forecast_service import simulate

AS_OF = date(2026, 6, 15)


def run(adjustments, transactions, recurring, classifications, balance_repo, horizon="90d"):
    return simulate(
        transactions,
        recurring,
        classifications,
        balance_repo,
        adjustments=adjustments,
        horizon=horizon,
        as_of=AS_OF,
    )


def test_percent_cut_improves_scenario(transactions, recurring, classifications, balance_repo):
    result = run(
        [AdjustCategory(category_main="Freizeit", category_sub="Gastronomie", percent=-50)],
        transactions, recurring, classifications, balance_repo,
    )
    assert result.diff.total_at_horizon_chf > 0
    assert result.diff.monthly_chf == pytest.approx(381.46 / 2, abs=0.5)
    assert result.scenario.free_to_spend.expected_chf > result.baseline.free_to_spend.expected_chf
    # The band scales along: a halved category contributes half its spread.
    assert (
        result.scenario.free_to_spend.upper_chf - result.scenario.free_to_spend.lower_chf
        < result.baseline.free_to_spend.upper_chf - result.baseline.free_to_spend.lower_chf
    )


def test_sub_none_adjusts_whole_main_category(transactions, recurring, classifications, balance_repo):
    result = run(
        [AdjustCategory(category_main="Freizeit", percent=-100)],
        transactions, recurring, classifications, balance_repo,
    )
    assert result.diff.monthly_chf == pytest.approx(483.37, abs=0.5)


def test_delta_shifts_monthly_total(transactions, recurring, classifications, balance_repo):
    result = run(
        [AdjustCategory(category_main="Freizeit", delta_chf=-150)],
        transactions, recurring, classifications, balance_repo,
    )
    assert result.diff.monthly_chf == pytest.approx(150, abs=0.01)


def test_effective_from_bends_curve_only_after_date(
    transactions, recurring, classifications, balance_repo
):
    effective = AS_OF + timedelta(days=30)
    result = run(
        [
            AdjustCategory(
                category_main="Freizeit",
                category_sub="Gastronomie",
                percent=-100,
                effective_from=effective,
            )
        ],
        transactions, recurring, classifications, balance_repo,
    )
    before = [p for p in result.diff.cumulative_series if p.date <= effective]
    after = [p for p in result.diff.cumulative_series if p.date > effective]
    assert all(p.diff_chf == 0 for p in before)
    assert after[-1].diff_chf > after[0].diff_chf > 0


def test_unknown_category_is_a_noop(transactions, recurring, classifications, balance_repo):
    result = run(
        [AdjustCategory(category_main="Gibtsnicht", percent=-50)],
        transactions, recurring, classifications, balance_repo,
    )
    assert result.diff.total_at_horizon_chf == 0
    assert result.diff.monthly_chf == 0


def test_percent_and_delta_are_mutually_exclusive():
    with pytest.raises(ValueError):
        AdjustCategory(category_main="Freizeit", percent=-50, delta_chf=-100)
    with pytest.raises(ValueError):
        AdjustCategory(category_main="Freizeit")
