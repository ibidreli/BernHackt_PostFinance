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
from app.repositories.transaction_repository import TransactionRepository

# T10 will mount the OData forecast routes here, e.g.:
#   from app.api.routes.forecast import router as forecast_router
#   app.include_router(forecast_router, prefix="/odata")


@asynccontextmanager
async def lifespan(app: FastAPI):
    raw = load_raw_transactions()
    app.state.raw_transactions = raw
    app.state.transaction_repository = TransactionRepository.from_raw(raw)
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
    }
