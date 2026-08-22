"""Assistant routes: the two OData resources behind the Assistenz page.

    POST /odata/Ask          - Action (complex body, one answer object)
    GET  /odata/Suggestions  - Function (read-only, Collection(Edm.String))

`Ask` is an Action rather than a Function for the same reason `Simulate`
is: OData Functions take their parameters in the URL, and the request
carries a nested assumptions/context body. Neither has side effects -
the service is read-only throughout - but an Action is the only shape
OData offers for a POST body.

The AI-backed version of this feature is not built yet. These routes are
the deterministic path: the numbers come from `forecast_service` and the
wording from templates, so the page works today and the model can be
slotted into `intent_service`/the phrasing step without the contract
changing.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from app.odata.envelope import odata_collection, odata_single
from app.schemas.assistant import AskEnvelope, AskRequest, AssistantHorizon, SuggestionsEnvelope
from app.services.assistant_service import SUGGESTIONS, ask as run_ask
from app.services.forecast_service import NoBalanceAvailableError

router = APIRouter()


@router.post(
    "/Ask",
    tags=["odata"],
    summary="Answer a question in natural language (OData Action)",
    description=(
        "Beantwortet genau drei Fragetypen (`affordability`, `what_if`, `time_to_goal`), "
        "alles andere mit `status=unsupported`. Die Antwort ist nie ein blosses Ja oder Nein, "
        "sondern `yes` / `tight` / `no_unless` - mit Fehlbetrag, nötigem Monatsbetrag und "
        "Hebeln aus echten variablen Kategorien.\n\n"
        "Gerechnet wird deterministisch über `forecast_service` - dieselbe Funktion, die auch "
        "`GetForecast`/`Simulate` aufrufen. Kein Betrag im Antworttext stammt aus einem "
        "Sprachmodell; alle werden gegen `facts` geprüft. `interest_applied` ist immer false.\n\n"
        "Gleiches 409-Verhalten wie GetForecast, wenn kein Saldo verfügbar ist."
    ),
    response_model=AskEnvelope,
)
def ask(request: Request, body: AskRequest) -> dict:
    try:
        result = run_ask(request.app.state, body)
    except NoBalanceAvailableError as exc:
        raise HTTPException(
            status_code=409,
            detail=f"Kein Saldo verfügbar für {exc.as_of.isoformat()} - bitte Startsaldo manuell eingeben.",
        ) from exc

    return odata_single("Ask", result.model_dump(mode="json"))


@router.get(
    "/Suggestions",
    tags=["odata"],
    summary="Suggested questions for a horizon (OData Function)",
    description=(
        "Chips für die Chat-Oberfläche, abhängig vom Horizont. Senkt die Hürde und lenkt auf "
        "die drei unterstützten Fragetypen. Uses a query parameter rather than the strict "
        "`Suggestions(horizon='5y')` path syntax, consistent with `GetForecast`."
    ),
    response_model=SuggestionsEnvelope,
)
def suggestions(horizon: AssistantHorizon = "5y") -> dict:
    return odata_collection("Suggestions", SUGGESTIONS[horizon])
