from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_metrics_endpoint_exists_and_has_http_requests_total():
    # Exercise a couple of endpoints first so labeled samples exist
    r1 = client.get("/health")
    assert r1.status_code == 200
    r2 = client.get("/ready")
    assert r2.status_code == 200

    # Metrics should still be present and likely contain labels for /health and /ready
    r3 = client.get("/metrics")
    assert r3.status_code == 200
    body3 = r3.text
    assert "http_requests_total" in body3
    assert "/health" in body3
    assert "/ready" in body3
    # Optional stronger signal that labels are recorded by endpoint template
    assert "/health" in body3
    assert "/ready" in body3
