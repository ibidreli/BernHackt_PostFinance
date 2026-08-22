"""Shared fixtures for the API test suite.

The env setup below MUST run before anything imports `app.main` or
`app.core.config`: config reads the environment at import time. pytest
imports conftest before any test module, so doing it here at module
level - not inside a fixture - is what makes the ordering reliable.

`ASSISTANT_MODE=cached` keeps the whole suite runnable without an
`OPENAI_API_KEY` (CI-friendly, per Projektstatus).
"""

from __future__ import annotations

import os
from pathlib import Path

os.environ["ASSISTANT_MODE"] = "cached"
os.environ.pop("OPENAI_API_KEY", None)
# Local checkout layout: <repo>/apps/api/tests -> <repo>/data/... In the
# container the tests sit at /app/tests and CSV_PATH is already set, so
# this default only fills in when the repo-relative file actually exists.
_repo_csv = Path(__file__).resolve().parent.joinpath("../../../data/data_personal.csv").resolve()
if _repo_csv.exists():
    os.environ.setdefault("CSV_PATH", str(_repo_csv))

import pytest  # noqa: E402

from app.data.data_personal import load_raw_transactions  # noqa: E402
from app.repositories.balance_repository import BalanceRepository  # noqa: E402
from app.repositories.transaction_repository import TransactionRepository  # noqa: E402
from app.services.classification import classify_transactions  # noqa: E402
from app.services.recurring_detection import detect_recurring_payments  # noqa: E402


@pytest.fixture(scope="session")
def transactions():
    return TransactionRepository.from_raw(load_raw_transactions()).all()


@pytest.fixture(scope="session")
def recurring(transactions):
    return detect_recurring_payments(transactions)


@pytest.fixture(scope="session")
def classifications(transactions, recurring):
    return classify_transactions(transactions, recurring)


@pytest.fixture(scope="session")
def balance_repo(transactions):
    return BalanceRepository(transactions)


@pytest.fixture(scope="session")
def client():
    """TestClient with lifespan - the startup hook loads the CSV and
    computes alerts exactly like the real service."""
    from fastapi.testclient import TestClient

    from app.main import app

    with TestClient(app) as test_client:
        yield test_client
