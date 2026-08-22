"""Golden tests for `forecast()` against the committed CSV.

The constants below were captured from a verified run (as_of fixed to
2026-06-15, well inside the CSV's date range) - they pin the whole
T1-T7 pipeline. If `data/data_personal.csv` ever changes, regenerate
them by printing the same fields from a fresh `forecast()` run; a diff
here after a pure refactor means the refactor changed behaviour.
"""

from __future__ import annotations

from datetime import date

import pytest

from app.services.forecast_service import forecast

AS_OF = date(2026, 6, 15)

GOLDEN = {
    "next_salary": {
        "horizon_end": "2026-06-25",
        "free_to_spend": (-403.56, -117.09, 138.68),
        "tight": ("2026-06-21", -58.26),
        "n_series": 11,
        "last_expected": -117.09,
        "n_known_payments": 0,
    },
    "30d": {
        "horizon_end": "2026-07-15",
        "free_to_spend": (-2165.09, -1305.68, -538.37),
        "tight": ("2026-06-21", -58.26),
        "n_series": 31,
        "last_expected": -1305.68,
        "n_known_payments": 1,
    },
    "90d": {
        "horizon_end": "2026-09-13",
        "free_to_spend": (-2030.4, -530.99, 807.75),
        "tight": ("2026-06-21", -58.26),
        "n_series": 91,
        "last_expected": -530.99,
        "n_known_payments": 13,
    },
    "365d": {
        "horizon_end": "2027-06-15",
        "free_to_spend": (-536.64, 2482.93, 5178.94),
        "tight": ("2026-06-21", -58.26),
        "n_series": 54,
        "last_expected": 2482.93,
        "n_known_payments": 77,
    },
}

OPENING_BALANCE = 459.7


@pytest.fixture(scope="module", params=sorted(GOLDEN))
def result(request, transactions, recurring, classifications, balance_repo):
    horizon = request.param
    return horizon, forecast(
        transactions, recurring, classifications, balance_repo, horizon=horizon, as_of=AS_OF
    )


def test_golden_numbers(result):
    horizon, f = result
    expected = GOLDEN[horizon]
    assert f.opening_balance_chf == OPENING_BALANCE
    assert f.horizon_end.isoformat() == expected["horizon_end"]
    assert (
        f.free_to_spend.lower_chf,
        f.free_to_spend.expected_chf,
        f.free_to_spend.upper_chf,
    ) == expected["free_to_spend"]
    assert f.tight_date is not None
    assert (f.tight_date.date.isoformat(), f.tight_date.projected_balance_chf) == expected["tight"]
    assert len(f.series) == expected["n_series"]
    assert f.series[-1].expected_chf == expected["last_expected"]
    assert len(f.known_payments) == expected["n_known_payments"]


def test_series_invariants(result):
    _, f = result
    assert f.series[0].date == AS_OF
    assert f.series[0].expected_chf == f.opening_balance_chf
    dates = [p.date for p in f.series]
    assert dates == sorted(dates)
    for point in f.series:
        assert point.lower_chf <= point.expected_chf <= point.upper_chf
