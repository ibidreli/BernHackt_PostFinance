"""The keyless demo path: `ASSISTANT_MODE=cached` (forced in conftest)
must answer the canned questions end-to-end without any LLM call -
which is also what makes this suite CI-safe."""

from __future__ import annotations


def test_cached_what_if_answers_without_api_key(client):
    response = client.post(
        "/api/v1/assistant/ask",
        json={"message": "Was wäre, wenn ich Netflix kündige?", "horizon": "present"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["source"] == "cached"
    assert body["intent"] == "what_if"
    assert body["answer"]


def test_cached_category_what_if_resolves_adjust_category(client):
    response = client.post(
        "/api/v1/assistant/ask",
        json={"message": "Was wäre, wenn ich Gastronomie halbiere?", "horizon": "1y"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["source"] == "cached"
    assert body["intent"] == "what_if"
    assert body["status"] != "unsupported"
    assert body["intervention"]["type"] == "adjust_category"
    assert body["intervention"]["category_main"] == "Freizeit"
    assert body["intervention"]["category_sub"] == "Gastronomie"
    assert body["intervention"]["percent"] == -50


def test_uncached_question_degrades_gracefully(client):
    response = client.post(
        "/api/v1/assistant/ask",
        json={"message": "Erzähl mir einen Witz über Steuern", "horizon": "present"},
    )
    # Cached mode is an exact-match fallback: unknown questions must not
    # 500 (and must not silently pretend to be a real answer).
    assert response.status_code == 200
    assert response.json()["source"] == "cached"


def test_suggestions_available_per_horizon(client):
    response = client.get("/api/v1/assistant/suggestions", params={"horizon": "5y"})
    assert response.status_code == 200
    assert len(response.json()["suggestions"]) >= 3
