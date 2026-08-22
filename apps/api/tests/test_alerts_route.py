"""HTTP tests for `GET /api/v1/Alerts` and the OData plumbing around it
(error envelope, strict unknown-field handling, scoped version header)."""

from __future__ import annotations

ALERT_TYPES = {"duplicate_charge", "large_payment", "category_spike"}
SEVERITIES = {"danger", "warning", "info"}


def test_alerts_envelope_shape(client):
    response = client.get("/api/v1/Alerts")
    assert response.status_code == 200
    body = response.json()
    assert body["@odata.context"].endswith("$metadata#Alerts")
    assert body["value"], "committed CSV is known to produce alerts"
    for alert in body["value"]:
        assert alert["type"] in ALERT_TYPES
        assert alert["severity"] in SEVERITIES


def test_filter_by_type(client):
    response = client.get("/api/v1/Alerts", params={"$filter": "type eq 'duplicate_charge'"})
    assert response.status_code == 200
    value = response.json()["value"]
    assert value
    assert {alert["type"] for alert in value} == {"duplicate_charge"}


def test_count_reports_prepaging_total(client):
    everything = client.get("/api/v1/Alerts").json()["value"]
    response = client.get("/api/v1/Alerts", params={"$count": "true", "$top": 1}).json()
    assert response["@odata.count"] == len(everything)
    assert len(response["value"]) == 1


def test_malformed_filter_is_400_with_odata_error_body(client):
    response = client.get("/api/v1/Alerts", params={"$filter": "type eq"})
    assert response.status_code == 400
    assert "message" in response.json()["error"]


def test_unknown_field_is_400(client):
    for params in (
        {"$filter": "typo eq 'x'"},
        {"$select": "typo"},
        {"$orderby": "typo desc"},
    ):
        response = client.get("/api/v1/Alerts", params=params)
        assert response.status_code == 400, params
        assert "Unknown field" in response.json()["error"]["message"]


def test_odata_version_header_only_on_odata_routes(client):
    assert client.get("/api/v1/Alerts").headers.get("OData-Version") == "4.0"
    assert client.get("/api/v1/$metadata").headers.get("OData-Version") == "4.0"
    assert "OData-Version" not in client.get("/health").headers
    assert "OData-Version" not in client.get("/api/v1/graph/months").headers


def test_graph_odata_routes_are_gone(client):
    assert client.get("/api/v1/GraphNodes").status_code == 404
    assert client.get("/api/v1/GraphMonths").status_code == 404
    assert b"GraphNode" not in client.get("/api/v1/$metadata").content
