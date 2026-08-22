"""Assistant tests: the state thresholds, lever selection, parameter
validation, the text-vs-facts number check, and the "text beats the
switcher" edge case.

Uses the real CSV through the app lifespan rather than fixtures - the
whole point of the feature is that nothing is mocked between the
question and `forecast_service`.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services import intent_service
from app.services.assistant_service import NON_DISCRETIONARY, _verify_numbers
from app.schemas.assistant import Facts


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


def ask(client, message: str, **kwargs) -> dict:
    body = {"message": message, "horizon": kwargs.pop("horizon", "5y"), **kwargs}
    response = client.post("/api/v1/assistant/ask", json=body)
    assert response.status_code == 200, response.text
    return response.json()


# --- supported vs. unsupported ----------------------------------------


@pytest.mark.parametrize(
    ("message", "intent"),
    [
        ("Kann ich mir in 5 Jahren ein Auto für 30'000 bar leisten?", "affordability"),
        ("Was wäre, wenn ich Gastronomie halbiere?", "what_if"),
        ("Wann habe ich 20'000 zusammen?", "time_to_goal"),
    ],
)
def test_three_supported_intents(client, message, intent):
    assert ask(client, message)["intent"] == intent


def test_everything_else_is_rejected_without_guessing(client):
    result = ask(client, "Wie ist das Wetter in Bern?")
    assert result["status"] == "unsupported"
    assert result["facts"] is None
    assert "drei" in result["answer"]


def test_answer_is_never_a_bare_yes_or_no(client):
    result = ask(client, "Kann ich mir in 5 Jahren ein Auto für 30'000 bar leisten?")
    assert result["status"] in ("yes", "tight", "no_unless")
    assert len(result["answer"]) > 40


# --- Antwortlogik ------------------------------------------------------


def test_no_unless_names_gap_monthly_amount_and_a_lever(client):
    result = ask(client, "Kann ich mir in 5 Jahren ein Haus für 900'000 bar leisten?")
    assert result["status"] == "no_unless"
    assert result["facts"]["gap_chf"] > 0
    assert result["facts"]["required_monthly_chf"] > 0
    assert result["levers"]


def test_levers_are_discretionary_variable_categories_only(client):
    levers = ask(client, "Kann ich mir in 5 Jahren ein Haus für 900'000 bar leisten?")["levers"]
    assert levers
    assert all(lever["category"] not in NON_DISCRETIONARY for lever in levers)
    assert levers == sorted(levers, key=lambda l: -l["monthly_avg_chf"])


def test_reachable_goal_reports_the_remaining_buffer(client):
    result = ask(client, "Kann ich mir in 10 Jahren ein Velo für 500 bar leisten?")
    assert result["status"] in ("yes", "tight")
    assert result["facts"]["buffer_after_months"] > 0


# --- Validierung / Rückfragen -----------------------------------------


def test_large_purchase_without_payment_type_asks_once(client):
    result = ask(client, "Kann ich mir ein Auto für 30'000 leisten?")
    assert result["status"] == "needs_clarification"
    assert result["clarification"]["field"] == "payment_type"
    assert result["clarification"]["options"] == ["Bar", "Leasing"]
    assert result["facts"] is None


def test_answered_clarification_is_not_asked_again(client):
    result = ask(
        client,
        "Kann ich mir ein Auto für 30'000 leisten?",
        context={"conversation_id": "t", "pending_clarification": "payment_type"},
    )
    assert result["status"] != "needs_clarification"


def test_missing_amount_triggers_a_question_not_an_assumption():
    extraction = intent_service.extract("Kann ich mir ein Auto leisten?", [])
    assert extraction.target_chf is None
    assert intent_service.validate(extraction, None).field == "target_chf"


def test_swiss_thousand_separators_parse():
    for text in ("für 30'000", "für 30 000", "für 30.000", "für 30000"):
        assert intent_service.extract(f"Kann ich mir ein Auto {text} bar leisten?", []).target_chf == 30000


# --- Annahmen ----------------------------------------------------------


def test_savings_rate_slider_moves_the_result(client):
    question = "Kann ich mir in 5 Jahren ein Auto für 30'000 bar leisten?"
    base = ask(client, question)
    raised = ask(client, question, assumptions={"salary_growth_pct": 1.0, "inflation_pct": 1.5, "savings_rate_pct": 30})
    assert raised["facts"]["projected_chf"] > base["facts"]["projected_chf"]
    assert raised["assumptions_used"]["savings_rate_pct"] == 30


def test_no_interest_is_ever_applied(client):
    assert ask(client, "Wann habe ich 20'000 zusammen?")["assumptions_used"]["interest_applied"] is False


# --- Horizonte und Charts ---------------------------------------------


@pytest.mark.parametrize("horizon", ["present", "1y", "5y", "10y"])
def test_all_four_horizons_answer(client, horizon):
    result = ask(client, "Kann ich mir ein Velo für 500 bar leisten?", horizon=horizon)
    assert result["chart"]["series"]


def test_horizon_in_the_text_beats_the_switcher(client):
    result = ask(client, "Kann ich mir in 5 Jahren ein Auto für 30'000 bar leisten?", horizon="1y")
    assert result["horizon"] == "5y"
    assert result["facts"]["months_remaining"] == 60


@pytest.mark.parametrize(
    ("message", "chart_type"),
    [
        ("Kann ich mir in 5 Jahren ein Auto für 30'000 bar leisten?", "wealth_over_time"),
        ("Wann habe ich 20'000 zusammen?", "goal_progress"),
        ("Was wäre, wenn ich Gastronomie halbiere?", "before_after"),
    ],
)
def test_chart_type_is_one_of_the_three_fixed_types(client, message, chart_type):
    assert ask(client, message)["chart"]["type"] == chart_type


def test_before_after_carries_both_curves(client):
    series = ask(client, "Was wäre, wenn ich Gastronomie halbiere?")["chart"]["series"]
    assert all(point["baseline_chf"] is not None for point in series)


# --- Zahlenabgleich ----------------------------------------------------


def test_amounts_in_the_text_must_exist_in_facts():
    facts = Facts(
        target_chf=30000,
        projected_chf=22600,
        gap_chf=7400,
        required_monthly_chf=125,
        months_remaining=60,
        buffer_after_months=1.4,
    )
    assert _verify_numbers("Dir fehlen CHF 7'400. Bei CHF 125 mehr pro Monat schaffst du es.", facts, [])
    assert not _verify_numbers("Dir fehlen CHF 7'900.", facts, [])


def test_every_generated_answer_passes_the_number_check(client):
    for message in (
        "Kann ich mir in 5 Jahren ein Auto für 30'000 bar leisten?",
        "Wann habe ich 20'000 zusammen?",
        "Kann ich mir in 10 Jahren ein Velo für 500 bar leisten?",
    ):
        result = ask(client, message)
        facts = Facts(**result["facts"])
        levers = [type("L", (), l)() for l in result["levers"]]
        assert _verify_numbers(result["answer"], facts, levers)
