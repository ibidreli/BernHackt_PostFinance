"""FastAPI application entrypoint.

No database: the bank export CSV is the source of truth and is loaded
once into memory at startup (see `lifespan` below). Repositories read
from `app.state` rather than a DB session.
"""

from __future__ import annotations

from collections import Counter
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request

from app.core.config import CSV_PATH
from app.data.data_personal import load_raw_transactions
from app.repositories.balance_repository import BalanceRepository
from app.repositories.transaction_repository import TransactionRepository, monthly_category_stats
from app.services.classification import classify_transactions
from app.services.forecast_service import forecast
from app.services.recurring_detection import detect_recurring_payments, detect_salary_day

# T10 will mount the OData forecast routes here, e.g.:
#   from app.api.routes.forecast import router as forecast_router
#   app.include_router(forecast_router, prefix="/odata")


@asynccontextmanager
async def lifespan(app: FastAPI):
    raw = load_raw_transactions()
    app.state.raw_transactions = raw
    repo = TransactionRepository.from_raw(raw)
    app.state.transaction_repository = repo
    app.state.balance_repository = BalanceRepository(repo.all())
    recurring_payments = detect_recurring_payments(repo.all())
    app.state.recurring_payments = recurring_payments
    app.state.classifications = classify_transactions(repo.all(), recurring_payments)
    yield


app = FastAPI(
    title="Forecast Service API",
    description=(
        "Zukunftsprognose & Szenario-Simulation. Read-only OData service "
        "over an in-memory snapshot of the account export - no database. "
        "See /odata/$metadata once T9/T10 land."
    ),
    version="0.1.0",
    lifespan=lifespan,
)


@app.get("/health", tags=["meta"])
def health(request: Request) -> dict:
    """Liveness probe that also proves the CSV was loaded and normalized
    at startup (raw load: T0, normalization: T1)."""
    df = request.app.state.raw_transactions
    repo: TransactionRepository = request.app.state.transaction_repository
    transactions = repo.all()
    flow_counts = Counter(t.flow for t in transactions)

    classifications = request.app.state.classifications
    variable_txs = [c.transaction for c in classifications if c.topf == "variable"]
    latest_balance = request.app.state.balance_repository.latest()
    category_stats = monthly_category_stats(variable_txs, as_of=latest_balance.as_of) if latest_balance else []

    return {
        "status": "ok",
        "csv_path": str(CSV_PATH),
        "rows_loaded": int(len(df)),
        "date_range": {
            "from": df["date"].min().date().isoformat(),
            "to": df["date"].max().date().isoformat(),
        },
        "transactions_normalized": len(transactions),
        "flow_counts": dict(flow_counts),
        "distinct_merchants": len({t.merchant for t in transactions}),
        "distinct_categories": len(
            {t.category_main for t in transactions if t.category_main}
        ),
        "sample_merchants": sorted({t.merchant for t in transactions})[:10],
        "recurring_payments_detected": len(request.app.state.recurring_payments),
        "recurring_payments_active": sum(
            1 for rp in request.app.state.recurring_payments if rp.is_active
        ),
        "recurring_intervals": dict(
            Counter(rp.interval for rp in request.app.state.recurring_payments)
        ),
        "salary_day": detect_salary_day(request.app.state.recurring_payments),
        "topf_counts": dict(Counter(c.topf for c in classifications)),
        "latest_balance": latest_balance.model_dump(mode="json") if latest_balance else None,
        "category_stats_computed": len(category_stats),
        "forecast_next_salary": _forecast_summary(request, "next_salary"),
    }


def _forecast_summary(request: Request, horizon: str) -> dict | None:
    """Proves T7 end-to-end: builds a real forecast through the full
    pipeline (T1-T7) and summarizes it, the same way T10's routes will."""
    try:
        f = forecast(
            request.app.state.transaction_repository.all(),
            request.app.state.recurring_payments,
            request.app.state.classifications,
            request.app.state.balance_repository,
            horizon=horizon,
        )
    except Exception as exc:  # noqa: BLE001 - health check should never 500
        return {"error": str(exc)}
    return {
        "horizon_end": f.horizon_end.isoformat(),
        "opening_balance_chf": f.opening_balance_chf,
        "free_to_spend": f.free_to_spend.model_dump(mode="json"),
        "tight_date": f.tight_date.model_dump(mode="json") if f.tight_date else None,
        "n_known_payments": len(f.known_payments),
        "n_series_points": len(f.series),
    }
