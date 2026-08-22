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
from app.schemas.forecast import ForecastEnvelope, Horizon, SimulateEnvelope, SimulateRequest
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


@router.get(
    "/RecurringPayments",
    tags=["odata"],
    summary="List recurring payments (OData EntitySet)",
    description=(
        "Active and inactive detected recurring payments (T3), each with the computed "
        "`recurring_id` needed for `cancel_recurring`/`adjust_recurring` in `POST /Simulate`. "
        "Supports the standard OData query options:\n\n"
        "- `$filter` - e.g. `is_active eq true and flow eq 'expense'`, `amount_chf gt 100` "
        "(operators: eq, ne, gt, ge, lt, le, and, or, not; string/number/bool/null literals; "
        "parentheses - see `app/odata/query.py` for the exact grammar)\n"
        "- `$select` - comma-separated field list, projects to a subset of fields\n"
        "- `$orderby` - `field` or `field desc`, comma-separated for multiple keys\n"
        "- `$top` / `$skip` - pagination\n"
        "- `$count=true` - adds `@odata.count` (total matches before `$top`/`$skip`)"
    ),
    # No response_model here: $select can project to an arbitrary subset
    # of fields, which a fixed Pydantic model can't represent - see
    # STATUS.md T11.
)
def list_recurring_payments(
    request: Request,
    odata_filter: str | None = Query(
        None, alias="$filter", description="e.g. `is_active eq true and flow eq 'expense'`"
    ),
    select: str | None = Query(None, alias="$select", description="e.g. `merchant,amount_chf`"),
    orderby: str | None = Query(None, alias="$orderby", description="e.g. `amount_chf desc`"),
    top: int | None = Query(None, alias="$top", ge=0),
    skip: int | None = Query(None, alias="$skip", ge=0),
    count: bool = Query(False, alias="$count", description="Include `@odata.count` in the response."),
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


@router.get(
    "/GetForecast",
    tags=["odata"],
    summary="Baseline forecast (OData Function)",
    description=(
        "Zukunftsprognose ohne Szenario. Verfügbarer Betrag als Korridor (P25/Median/P75), "
        "kumulierte Saldokurve, Engpass-Datum aus der pessimistischen Bandgrenze. "
        "OData Function - GET, read-only, no side effects. Uses query parameters "
        "(`?horizon=...&as_of=...`) rather than the strict OData `GetForecast(horizon='...')` "
        "path syntax - see module docstring.\n\n"
        "Returns 409 if no balance is available as of `as_of` (issue's \"Kein Saldo "
        'vorhanden" edge case) - the frontend should then prompt for a manual starting balance.'
    ),
    response_model=ForecastEnvelope,
)
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


@router.post(
    "/Simulate",
    tags=["odata"],
    summary="Baseline + scenario forecast with adjustments (OData Action)",
    description=(
        "Prognose mit Eingriffen (cancel_recurring/adjust_recurring/add_recurring/one_off, "
        "einzeln oder kombiniert). Liefert Baseline und Szenario in einer Antwort, damit das "
        "Frontend beide Kurven ohne zweiten Request zeichnen kann - plus `diff` "
        "(scenario - baseline, \"positiv = besser\"). "
        "OData Action - POST, complex body, the correct OData shape for an operation with "
        "side-effect-style input (as opposed to a Function).\n\n"
        "`recurring_id` values come from `GET /RecurringPayments`. "
        "Same 409 behaviour as GetForecast if no balance is available."
    ),
    response_model=SimulateEnvelope,
)
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
