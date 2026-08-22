from __future__ import annotations

from datetime import date

from fastapi import APIRouter, HTTPException, Query, Request

from app.schemas.graph import GraphFlow, GraphMode, GraphMonthsResponse, GraphResponse
from app.services.graph_service import available_months, build_graph

router = APIRouter()


@router.get("/graph", tags=["graph"], response_model=GraphResponse)
def get_graph(
    request: Request,
    month: str | None = Query(None, description="YYYY-MM"),
    mode: GraphMode = Query("absolute"),
    flow: GraphFlow = Query("expense"),
) -> GraphResponse:
    repo = request.app.state.transaction_repository
    transactions = repo.all()
    months = available_months(transactions, limit=0)

    effective_month = month
    if effective_month is None:
        effective_month = months[-1] if months else date.today().strftime("%Y-%m")

    try:
        return build_graph(transactions, month=effective_month, mode=mode, flow=flow)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/graph/months", tags=["graph"], response_model=GraphMonthsResponse)
def get_graph_months(request: Request) -> GraphMonthsResponse:
    repo = request.app.state.transaction_repository
    months = available_months(repo.all(), limit=12)
    default = months[-1] if months else None
    return GraphMonthsResponse(months=months, default=default)
