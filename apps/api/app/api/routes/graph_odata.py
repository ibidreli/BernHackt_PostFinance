"""OData routes for graph exploration with server-side drilldown filtering."""

from __future__ import annotations

from datetime import date
from types import SimpleNamespace

from fastapi import APIRouter, HTTPException, Query, Request

from app.odata.envelope import odata_collection
from app.odata.query import ODataFilterError, apply_query_options
from app.schemas.graph import GraphFlow, GraphMode
from app.services.graph_service import available_months, build_graph, flatten_graph_nodes

router = APIRouter()

_DEFAULT_GRAPH_SELECT = (
    "node_id,parent_id,month,mode,node_type,level,label,flow,amount_chf,"
    "transaction_count,rank,merchant_count,category_main,category_sub,merchant,"
    "has_children,delta_baseline_median_chf,delta_diff_chf,delta_diff_pct,delta_direction,"
    "summary_child_count,summary_transaction_count,summary_total_amount_chf,summary_avg_amount_chf"
)


@router.get(
    "/GraphNodes",
    tags=["odata"],
    summary="Graph nodes (OData EntitySet, drilldown-ready)",
    description=(
        "Flattened graph nodes for a month/mode/flow. Use `$filter` for drilldown "
        "(e.g. merchants of one category) and `$select` to keep payload small. "
        "Set `include_transactions=true` only when transaction leaf details are needed."
    ),
)
def list_graph_nodes(
    request: Request,
    month: str | None = Query(None, description="YYYY-MM; default latest available month."),
    mode: GraphMode = Query("absolute"),
    flow: GraphFlow = Query("expense"),
    include_transactions: bool = Query(False, description="Include full tx_* detail columns."),
    max_level: int | None = Query(None, ge=0, le=3, description="Optional server-side level cutoff."),
    odata_filter: str | None = Query(None, alias="$filter"),
    select: str | None = Query(None, alias="$select"),
    orderby: str | None = Query(None, alias="$orderby"),
    top: int | None = Query(None, alias="$top", ge=0),
    skip: int | None = Query(None, alias="$skip", ge=0),
    count: bool = Query(False, alias="$count"),
) -> dict:
    repo = request.app.state.transaction_repository
    transactions = repo.all()
    months = available_months(transactions, limit=0)
    effective_month = month or (months[-1] if months else date.today().strftime("%Y-%m"))

    try:
        graph = build_graph(transactions, month=effective_month, mode=mode, flow=flow)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    rows = flatten_graph_nodes(graph, include_transactions=include_transactions)
    if max_level is not None:
        rows = [row for row in rows if getattr(row, "level") <= max_level]

    try:
        result = apply_query_options(
            rows,
            filter_=odata_filter,
            select=select or _DEFAULT_GRAPH_SELECT,
            orderby=orderby,
            top=top,
            skip=skip,
        )
    except ODataFilterError as exc:
        raise HTTPException(status_code=400, detail=f"Invalid $filter: {exc}") from exc

    items = [vars(it) if isinstance(it, SimpleNamespace) else it for it in result.items]
    return odata_collection("GraphNodes", items, count=result.count if count else None)


@router.get(
    "/GraphMonths",
    tags=["odata"],
    summary="Available graph months (OData EntitySet)",
    description="Available months for graph exploration (latest 12).",
)
def list_graph_months(
    request: Request,
    odata_filter: str | None = Query(None, alias="$filter"),
    select: str | None = Query(None, alias="$select"),
    orderby: str | None = Query(None, alias="$orderby"),
    top: int | None = Query(None, alias="$top", ge=0),
    skip: int | None = Query(None, alias="$skip", ge=0),
    count: bool = Query(False, alias="$count"),
) -> dict:
    repo = request.app.state.transaction_repository
    months = available_months(repo.all(), limit=12)
    default = months[-1] if months else None
    entities = [
        SimpleNamespace(month=month, is_default=(month == default), sort_key=index)
        for index, month in enumerate(months)
    ]
    try:
        result = apply_query_options(
            entities,
            filter_=odata_filter,
            select=select or "month,is_default,sort_key",
            orderby=orderby or "sort_key",
            top=top,
            skip=skip,
        )
    except ODataFilterError as exc:
        raise HTTPException(status_code=400, detail=f"Invalid $filter: {exc}") from exc

    items = [vars(it) if isinstance(it, SimpleNamespace) else it for it in result.items]
    return odata_collection("GraphMonths", items, count=result.count if count else None)

