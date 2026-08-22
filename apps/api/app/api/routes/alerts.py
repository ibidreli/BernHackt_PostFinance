"""OData EntitySet for conservative transaction alerts."""

from __future__ import annotations

from types import SimpleNamespace

from fastapi import APIRouter, HTTPException, Query, Request

from app.odata.envelope import odata_collection
from app.odata.query import ODataFilterError, apply_query_options

router = APIRouter()

_DEFAULT_ALERT_SELECT = (
    "alert_id,type,severity,date,month,merchant,category_main,category_sub,"
    "amount_chf,baseline_chf,count,booking_text,transaction_id,transaction_ids"
)


@router.get(
    "/Alerts",
    tags=["odata"],
    summary="List detected alerts (OData EntitySet)",
    description=(
        "Deterministic alerts computed once at startup from the loaded CSV. "
        "Supports `$filter`, `$select`, `$orderby`, `$top`, `$skip`, and `$count`."
    ),
)
def list_alerts(
    request: Request,
    odata_filter: str | None = Query(None, alias="$filter"),
    select: str | None = Query(None, alias="$select"),
    orderby: str | None = Query(None, alias="$orderby"),
    top: int | None = Query(None, alias="$top", ge=0),
    skip: int | None = Query(None, alias="$skip", ge=0),
    count: bool = Query(False, alias="$count"),
) -> dict:
    entities = [
        SimpleNamespace(**alert.model_dump(mode="json"))
        for alert in request.app.state.alerts
    ]
    try:
        result = apply_query_options(
            entities,
            filter_=odata_filter,
            select=select or _DEFAULT_ALERT_SELECT,
            orderby=orderby,
            top=top,
            skip=skip,
        )
    except ODataFilterError as exc:
        raise HTTPException(status_code=400, detail=f"Invalid $filter: {exc}") from exc

    items = [
        vars(item) if isinstance(item, SimpleNamespace) else item
        for item in result.items
    ]
    return odata_collection("Alerts", items, count=result.count if count else None)
