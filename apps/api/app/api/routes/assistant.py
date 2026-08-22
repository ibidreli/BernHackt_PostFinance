"""REST routes for the Future-Me Chatbot (Feature #5, T11) - the issue's
own API contract literally (`POST /api/v1/assistant/ask`,
`GET /api/v1/assistant/suggestions`), not folded into Feature #4's
OData subset - your explicit decision when this feature was planned,
documented in ASSISTANT_STATUS.md.

Both LLM-call failure modes (T3's/T7's `AssistantLLMTimeoutError`,
`AssistantLLMError`) surface here as explicit HTTP errors - per your
instruction, never a silent fallback that pretends to work. Error
bodies still come out in the OData JSON error shape
(`{"error": {"code", "message"}}`) because `install_odata_error_handlers`
(Feature #4, T9) is installed service-wide in `main.py` - a deliberate
pre-existing choice ("harmless on non-OData endpoints", see
`app/odata/envelope.py`), kept here for one consistent error format
across the whole API rather than inventing a second one.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from app.schemas.assistant import AssistantAskRequest, AssistantAskResponse, AssistantHorizon, SuggestionsResponse
from app.services.assistant_service import ask as run_ask
from app.services.forecast_service import NoBalanceAvailableError
from app.services.llm_client import AssistantLLMError, AssistantLLMTimeoutError

router = APIRouter()

# Chip suggestions per horizon (issue: "Drei bis fünf vorgeschlagene
# Fragen... abhängig vom gewählten Horizont"). Deliberately natural,
# varied phrasing per tab rather than forcing every entry to be one of
# T9's 5 cached demo questions - GET /suggestions is a general UX helper
# for live mode, not a cached-mode contract; a chip that doesn't happen
# to match the cached set still degrades gracefully (T9's
# `_CACHED_NO_MATCH_PREFIX` names the real options). Most entries here
# ARE cached-question matches anyway (verified live during T5-T10),
# only the 10y affordability example isn't.
SUGGESTIONS_BY_HORIZON: dict[str, list[str]] = {
    "present": [
        "Kann ich mir jetzt Kopfhörer für 300 leisten?",
        "Was wäre, wenn ich Netflix kündige?",
        "Was wäre, wenn ich monatlich 50 mehr für Fitness ausgebe?",
    ],
    "1y": [
        "Wann habe ich 20000 zusammen?",
        "Was wäre, wenn ich Netflix kündige?",
        "Was wäre, wenn ich monatlich 50 mehr für Fitness ausgebe?",
    ],
    "5y": [
        "Kann ich mir in 5 Jahren ein Auto für 30000 leisten?",
        "Wann habe ich 20000 zusammen?",
        "Was wäre, wenn ich Netflix kündige?",
    ],
    "10y": [
        "Kann ich mir in 10 Jahren einen Töff für 8000 leisten?",
        "Wann habe ich 20000 zusammen?",
        "Was wäre, wenn ich Netflix kündige?",
    ],
}


@router.post(
    "/assistant/ask",
    tags=["assistant"],
    summary="Future-Me Chatbot: Frage stellen",
    description=(
        "Nimmt eine Nutzerfrage entgegen, extrahiert strukturierte Parameter (LLM-Call #1, T3), "
        "berechnet über forecast_service (Feature #4/T2, T5) und formuliert die Antwort "
        "(LLM-Call #2, T7) - inkl. automatischem Zahlenabgleich gegen die berechneten `facts` "
        "(T10) und Fallback auf eine garantiert korrekte Template-Formulierung bei Abweichung.\n\n"
        "`ASSISTANT_MODE=cached` (T9) beantwortet nur die 5 vorbereiteten Demo-Fragen ohne "
        "jeden externen API-Call - `forecast_service` rechnet dabei trotzdem echt.\n\n"
        "**Fehler:** 409 wenn kein Saldo verfügbar ist (gleiches Verhalten wie "
        "`GET /api/v1/GetForecast`). 504/502, falls einer der beiden LLM-Calls fehlschlägt - "
        "bewusst kein stiller Fallback, der wie eine normale Antwort aussieht (siehe "
        "ASSISTANT_STATUS.md, T9)."
    ),
    response_model=AssistantAskResponse,
)
def ask(request: Request, body: AssistantAskRequest) -> AssistantAskResponse:
    state = request.app.state
    try:
        return run_ask(
            body,
            state.transaction_repository.all(),
            state.recurring_payments,
            state.classifications,
            state.balance_repository,
            state.conversation_store,
        )
    except NoBalanceAvailableError as exc:
        raise HTTPException(
            status_code=409,
            detail=f"Kein Saldo verfügbar für {exc.as_of.isoformat()} - bitte Startsaldo manuell eingeben.",
        ) from exc
    except AssistantLLMTimeoutError as exc:
        raise HTTPException(
            status_code=504,
            detail=f"{exc.stage} hat zu lange gedauert (> {exc.seconds}s). Bitte erneut versuchen.",
        ) from exc
    except AssistantLLMError as exc:
        raise HTTPException(status_code=502, detail=f"Anfrage an das Sprachmodell fehlgeschlagen: {exc}") from exc


@router.get(
    "/assistant/suggestions",
    tags=["assistant"],
    summary="Vorschlags-Chips für den gewählten Horizont",
    description="Drei vorformulierte Fragen passend zum Horizont, als Chips im Chat-UI gedacht.",
    response_model=SuggestionsResponse,
)
def suggestions(horizon: AssistantHorizon = "present") -> SuggestionsResponse:
    return SuggestionsResponse(horizon=horizon, suggestions=SUGGESTIONS_BY_HORIZON[horizon])
