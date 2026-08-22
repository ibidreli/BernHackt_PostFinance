"""Assistant routes (Feature 3). Plain REST under `/api/v1/assistant`,
not OData: unlike the forecast resources these two endpoints aren't
entity sets or typed functions over the data model - they're a
conversational operation, and forcing them into an OData Action would
add ceremony without adding a queryable resource.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from app.schemas.assistant import AskRequest, AskResponse, AssistantHorizon, SuggestionsResponse
from app.services.assistant_service import SUGGESTIONS, ask as run_ask
from app.services.forecast_service import NoBalanceAvailableError

router = APIRouter(tags=["assistant"])


@router.post(
    "/ask",
    summary="Answer a question in natural language",
    description=(
        "Beantwortet genau drei Fragetypen (`affordability`, `what_if`, `time_to_goal`), "
        "alles andere mit `status=unsupported`. Die Antwort ist nie ein blosses Ja oder Nein, "
        "sondern `yes` / `tight` / `no_unless` - mit Fehlbetrag, nötigem Monatsbetrag und "
        "Hebeln aus echten variablen Kategorien.\n\n"
        "Gerechnet wird deterministisch über `forecast_service` - dieselbe Funktion, die auch "
        "der Slider aus Feature 2 aufruft. Kein Betrag im Antworttext stammt aus einem "
        "Sprachmodell; alle werden gegen `facts` geprüft. `interest_applied` ist immer false."
    ),
    response_model=AskResponse,
)
def ask(request: Request, body: AskRequest) -> AskResponse:
    try:
        return run_ask(request.app.state, body)
    except NoBalanceAvailableError as exc:
        raise HTTPException(
            status_code=409,
            detail=f"Kein Saldo verfügbar für {exc.as_of.isoformat()} - bitte Startsaldo manuell eingeben.",
        ) from exc


@router.get(
    "/suggestions",
    summary="Suggested questions for a horizon",
    description="Chips für die Chat-Oberfläche. Senkt die Hürde und lenkt auf die drei unterstützten Fragetypen.",
    response_model=SuggestionsResponse,
)
def suggestions(horizon: AssistantHorizon = "5y") -> SuggestionsResponse:
    return SuggestionsResponse(horizon=horizon, suggestions=SUGGESTIONS[horizon])
