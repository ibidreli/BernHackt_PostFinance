"""FastAPI application entrypoint.

No database: the bank export CSV is the source of truth and is loaded
once into memory at startup (see `lifespan` below). Repositories read
from `app.state` rather than a DB session.
"""

from __future__ import annotations

from collections import Counter
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes.assistant import router as assistant_router
from app.api.routes.alerts import router as alerts_router
from app.api.routes.forecast import router as forecast_router
from app.api.routes.graph import router as graph_router
from app.core.config import ASSISTANT_MODE, CSV_PATH, OPENAI_API_KEY
from app.data.data_personal import load_raw_transactions
from app.odata.envelope import ODataVersionMiddleware, install_odata_error_handlers
from app.odata.metadata import METADATA_XML
from app.repositories.balance_repository import BalanceRepository
from app.repositories.transaction_repository import TransactionRepository, monthly_category_stats
from app.services.classification import classify_transactions
from app.services.alert_service import build_alerts
from app.services.conversation_state import ConversationStore
from app.services.forecast_service import forecast
from app.services.recurring_detection import detect_recurring_payments, detect_salary_day


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Feature #5 (Future-Me Chatbot): fail fast, same philosophy as the
    # missing-CSV case below - a cryptic per-request OpenAI auth error deep
    # inside a chat request is a worse failure mode during the pitch than
    # the container refusing to start with a clear message. Only required
    # in "live" mode; ASSISTANT_MODE=cached needs no key at all.
    if ASSISTANT_MODE == "live" and not OPENAI_API_KEY:
        raise RuntimeError(
            "OPENAI_API_KEY fehlt (ASSISTANT_MODE=live). Entweder "
            "apps/api/app/.env setzen (siehe .env.example) oder "
            "ASSISTANT_MODE=cached fuer den Offline-Fallback verwenden."
        )

    raw = load_raw_transactions()
    app.state.raw_transactions = raw
    repo = TransactionRepository.from_raw(raw)
    app.state.transaction_repository = repo
    app.state.balance_repository = BalanceRepository(repo.all())
    recurring_payments = detect_recurring_payments(repo.all())
    app.state.recurring_payments = recurring_payments
    app.state.classifications = classify_transactions(repo.all(), recurring_payments)
    app.state.alerts = build_alerts(repo.all(), app.state.classifications)
    # Feature #5 (T4): in-memory conversation state for Folgefragen +
    # multi-turn Rückfragen - see app/services/conversation_state.py.
    # Fresh on every restart, same "no database" philosophy as everything
    # else here.
    app.state.conversation_store = ConversationStore()
    yield


app = FastAPI(
    title="Forecast Service API",
    description=(
        "Zukunftsprognose & Szenario-Simulation. Read-only OData service "
        "over an in-memory snapshot of the account export - no database. "
        "See /api/v1/$metadata for the CSDL, /docs for interactive Swagger UI."
    ),
    version="0.1.0",
    lifespan=lifespan,
)
app.add_middleware(ODataVersionMiddleware)
install_odata_error_handlers(app)
app.include_router(graph_router, prefix="/api/v1")
app.include_router(forecast_router, prefix="/api/v1")
app.include_router(alerts_router, prefix="/api/v1")
app.include_router(assistant_router, prefix="/api/v1")

# Read-only service over a local CSV, no auth and no cookies - the
# Angular dev server (a different origin) needs to reach it directly
# when it isn't proxying.
app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"]
)


@app.get("/api/v1/$metadata", tags=["odata"], include_in_schema=False)
def odata_metadata() -> Response:
    """CSDL service document for all exposed OData resources."""
    return Response(content=METADATA_XML, media_type="application/xml")


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
        "alert_counts": dict(Counter(a.type for a in request.app.state.alerts)),
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
