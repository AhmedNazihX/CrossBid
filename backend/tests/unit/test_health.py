"""The liveness probe. Compose, the Dockerfile HEALTHCHECK and CI all depend on it."""

from __future__ import annotations

from fastapi.testclient import TestClient


def test_health_reports_ok(client: TestClient) -> None:
    # Arrange / Act
    response = client.get("/health")

    # Assert
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "crossbid-api"}


def test_openapi_schema_is_served(client: TestClient) -> None:
    """The schema is the contract the frontend's types are generated from (S0.4.2)."""
    # Act
    response = client.get("/openapi.json")

    # Assert
    assert response.status_code == 200
    schema = response.json()
    assert schema["info"]["title"] == "Crossbid API"
    assert "/health" in schema["paths"]


def test_unknown_route_is_404(client: TestClient) -> None:
    # Act / Assert
    assert client.get("/no-such-route").status_code == 404
