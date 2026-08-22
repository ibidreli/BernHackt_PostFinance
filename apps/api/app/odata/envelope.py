"""OData v4 response envelope, error format, and version header (T9).

Deliberately NOT full OData protocol compliance - no `$batch`, no Atom/
XML representation (modern OData services are JSON-only in practice too).
Covers the parts that are cheap and give the clearest "this is really
OData" signal: the `OData-Version` header on every response, the
`@odata.context` envelope on collection/function/action results, and the
standard OData JSON error shape instead of FastAPI's default
`{"detail": ...}`.
"""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.base import BaseHTTPMiddleware

SERVICE_ROOT = "/odata"


def odata_collection(context_suffix: str, value: list[Any], count: int | None = None) -> dict:
    """Envelope for an EntitySet listing or a Collection-typed Function
    result: `{"@odata.context": ..., ["@odata.count": N,] "value": [...]}`.
    `count` is included only when the caller passed `$count=true`."""
    body: dict[str, Any] = {"@odata.context": f"{SERVICE_ROOT}/$metadata#{context_suffix}"}
    if count is not None:
        body["@odata.count"] = count
    body["value"] = value
    return body


def odata_single(context_suffix: str, value: dict) -> dict:
    """Envelope for a single-entity/complex-type result (Function/Action
    returning one object, not a collection)."""
    return {"@odata.context": f"{SERVICE_ROOT}/$metadata#{context_suffix}", **value}


class ODataVersionMiddleware(BaseHTTPMiddleware):
    """Stamps every response with `OData-Version: 4.0`. Applied
    service-wide rather than only under /odata for simplicity - harmless
    on non-OData endpoints like /health, and the spec only says OData
    responses must carry it, not that others mustn't."""

    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        response.headers["OData-Version"] = "4.0"
        return response


def install_odata_error_handlers(app: FastAPI) -> None:
    """Replaces FastAPI's default error bodies with the OData v4 JSON
    error shape: `{"error": {"code", "message", ["details"]}}`. Applied
    service-wide for the same reason as the version middleware."""

    @app.exception_handler(StarletteHTTPException)
    async def _http_exception_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content={"error": {"code": str(exc.status_code), "message": str(exc.detail)}},
        )

    @app.exception_handler(RequestValidationError)
    async def _validation_exception_handler(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        return JSONResponse(
            status_code=422,
            content={
                "error": {
                    "code": "422",
                    "message": "Validation failed",
                    "details": [
                        {"message": e["msg"], "target": ".".join(str(p) for p in e["loc"])}
                        for e in exc.errors()
                    ],
                }
            },
        )
