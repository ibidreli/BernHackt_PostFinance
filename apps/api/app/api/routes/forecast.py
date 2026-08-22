"""OData routes for the forecast feature (T10): the three endpoints from
the issue's API contract, mapped onto OData concepts per the earlier
architecture decision:

    GET  /odata/RecurringPayments  - EntitySet, full $filter/$select/
                                      $orderby/$top/$skip/$count
    GET  /odata/GetForecast        - Function (read-only, no side effects)
    POST /odata/Simulate           - Action (side-effect-capable, complex body)

Deviates from strict OData URL syntax for GetForecast: the spec calls for
parenthetical parameters in the path (`GetForecast(horizon='30d')`), this
uses query parameters instead (`?horizon=30d`) - consistent with the
pragmatic OData subset decision (see STATUS.md), and keeps FastAPI's
Swagger UI usable for these parameters instead of a raw path string that
would need manual parsing.
"""

from __future__ import annotations

from datetime import date
from types import SimpleNamespace
from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request

from app.odata.envelope import odata_collection, odata_single
from app.odata.query import ODataFilterError, apply_query_options
from app.schemas.forecast import Horizon, SimulateRequest
from app.services.forecast_service import NoBalanceAvailableError
from app.services.forecast_service import forecast as run_forecast
from app.services.forecast_service import simulate as run_simulate
from app.services.recurring_detection import recurring_payment_id

router = APIRouter()


def _no_balance_error(exc: NoBalanceAvailableError) -> HTTPException:
    # Issue's "Kein Saldo vorhanden" edge case: 409 (state conflict, not
    # a client input error) with a message the frontend can show directly
    # next to the manual-starting-balance input field it must offer.
    return HTTPException(
        status_code=409,
        detail=f"Kein Saldo verfügbar für {exc.as_of.isoformat()} - bitte Startsaldo manuell eingeben.",
    )


# --- GET /RecurringPayments (EntitySet) --------------------------------


def _to_entity(rp: Any) -> SimpleNamespace:
    """Flattens a RecurringPayment into a namespace that also carries its
    computed `recurring_id` (not a real model field, see
    `app/services/recurring_detection.py::recurring_payment_id`) so
    `$filter`/`$select`/`$orderby` can reference it like any other
    property."""
    data = rp.model_dump(mode="json")
    data["recurring_id"] = recurring_payment_id(rp)
    return SimpleNamespace(**data)


@router.get("/RecurringPayments", tags=["odata"])
def list_recurring_payments(
    request: Request,
    odata_filter: str | None = Query(None, alias="$filter"),
    select: str | None = Query(None, alias="$select"),
    orderby: str | None = Query(None, alias="$orderby"),
    top: int | None = Query(None, alias="$top", ge=0),
    skip: int | None = Query(None, alias="$skip", ge=0),
    count: bool = Query(False, alias="$count"),
) -> dict:
    entities = [_to_entity(rp) for rp in request.app.state.recurring_payments]
    try:
        result = apply_query_options(
            entities, filter_=odata_filter, select=select, orderby=orderby, top=top, skip=skip
        )
    except ODataFilterError as exc:
        raise HTTPException(status_code=400, detail=f"Invalid $filter: {exc}") from exc

    items = [vars(it) if isinstance(it, SimpleNamespace) else it for it in result.items]
    return odata_collection("RecurringPayments", items, count=result.count if count else None)


# --- GET /GetForecast (Function) ---------------------------------------


@router.get("/GetForecast", tags=["odata"])
def get_forecast(
    request: Request,
    horizon: Horizon = "next_salary",
    as_of: date | None = None,
) -> dict:
    state = request.app.state
    try:
        result = run_forecast(
            state.transaction_repository.all(),
            state.recurring_payments,
            state.classifications,
            state.balance_repository,
            horizon=horizon,
            as_of=as_of,
        )
    except NoBalanceAvailableError as exc:
        raise _no_balance_error(exc) from exc

    return odata_single("GetForecast", result.model_dump(mode="json"))


# --- POST /Simulate (Action) -------------------------------------------


@router.post("/Simulate", tags=["odata"])
def simulate(request: Request, body: SimulateRequest) -> dict:
    state = request.app.state
    try:
        result = run_simulate(
            state.transaction_repository.all(),
            state.recurring_payments,
            state.classifications,
            state.balance_repository,
            adjustments=body.adjustments,
            horizon=body.horizon,
            as_of=body.as_of,
        )
    except NoBalanceAvailableError as exc:
        raise _no_balance_error(exc) from exc

    return odata_single("Simulate", result.model_dump(mode="json"))
