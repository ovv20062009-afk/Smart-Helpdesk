from datetime import datetime
from pathlib import Path
from unittest.mock import patch
from uuid import UUID

from fastapi.testclient import TestClient
import pytest

from src.api import create_app, get_limiter
from src.limiter import MemoryRateLimiter
from src.prediction import Decision
from src.schemas import PredictionOutput

ROOT = Path(__file__).resolve().parents[1]
PAYLOAD = {"ticket_id": "T-7", "text": "Не могу войти, забыла пароль", "channel": "web"}
HEADERS = {"Authorization": "Bearer unit-test-only"}


@pytest.fixture
def client():
    with TestClient(create_app(ROOT)) as session:
        yield session


def test_real_artifact_contract(client):
    response = client.post("/api/v1/predict", json=PAYLOAD, headers=HEADERS)
    assert response.status_code == 200
    body = PredictionOutput.model_validate(response.json())
    assert body.prediction.category == "TECHNICAL"
    assert 0 <= body.prediction.confidence <= 1
    assert body.metadata.source == "model" and body.metadata.degraded is False
    assert body.prediction.threshold_used == 0.8
    assert body.metadata.timestamp_utc.utcoffset().total_seconds() == 0
    assert body.trace_id.version == 4
    assert response.headers["X-Trace-ID"] == str(body.trace_id)


@pytest.mark.parametrize("headers", [{}, {"Authorization": "Bearer wrong"}, {"Authorization": "Basic abc"}])
@pytest.mark.parametrize("path", ["/predict", "/api/v1/predict"])
def test_missing_wrong_and_wrong_scheme(client, headers, path):
    response = client.post(path, json=PAYLOAD, headers=headers)
    assert response.status_code == 401
    assert response.headers["WWW-Authenticate"] == "Bearer"
    assert response.json()["trace_id"] == response.headers["X-Trace-ID"]
    assert not client.app.state.limiter.history


@pytest.mark.parametrize("path", ["/predict", "/api/v1/predict"])
def test_readonly_client_really_forbidden(client, path):
    response = client.post(path, json=PAYLOAD, headers={"Authorization": "Bearer unit-readonly-only"})
    assert response.status_code == 403
    assert not client.app.state.limiter.history


@pytest.mark.parametrize("field", ["ticket_id", "text"])
def test_missing_required_field(client, field):
    payload = dict(PAYLOAD)
    del payload[field]
    assert client.post("/api/v1/predict", json=payload, headers=HEADERS).status_code == 422


@pytest.mark.parametrize("change", [
    {"text": ""}, {"text": "  "}, {"text": "!123"}, {"text": 42},
    {"text": "я" * 5001}, {"channel": "sms"}, {"channel": None},
    {"ticket_id": ""}, {"ticket_id": "a" * 101}, {"ticket_id": "../x"},
    {"ticket_id": 123}, {"unexpected": "secret"},
])
def test_invalid_inputs(client, change):
    response = client.post("/api/v1/predict", json={**PAYLOAD, **change}, headers=HEADERS)
    assert response.status_code == 422
    assert "secret" not in response.text


def test_nan_input_rejected(client):
    response = client.post("/api/v1/predict", content='{"ticket_id":"T-7","text":NaN}',
                           headers={**HEADERS, "Content-Type": "application/json"})
    assert response.status_code == 422


def test_valid_boundaries_and_channel_default(client):
    for length in (1, 5000):
        response = client.post("/api/v1/predict", json={"ticket_id": "T" * 100, "text": "я" * length}, headers=HEADERS)
        assert response.status_code == 200
        PredictionOutput.model_validate(response.json())


def test_shared_quota_and_expiry(client):
    now = [0.0]
    limiter = MemoryRateLimiter(2, 60, clock=lambda: now[0])
    client.app.dependency_overrides[get_limiter] = lambda: limiter
    for path in ("/predict", "/api/v1/predict"):
        assert client.post(path, json=PAYLOAD, headers=HEADERS).status_code == 200
    now[0] = 40.2
    response = client.post("/api/v1/predict", json=PAYLOAD, headers=HEADERS)
    assert response.status_code == 429
    assert response.headers["Retry-After"] == "20"
    assert response.json()["trace_id"] == response.headers["X-Trace-ID"]
    assert client.get("/health").status_code == 200
    assert client.get("/ready").status_code == 200
    now[0] = 60
    assert client.post("/api/v1/predict", json=PAYLOAD, headers=HEADERS).status_code == 200


def test_admitted_invalid_input_counts_in_quota(client):
    client.app.dependency_overrides[get_limiter] = lambda: limiter
    limiter = MemoryRateLimiter(1)
    assert client.post("/api/v1/predict", json={**PAYLOAD, "text": ""}, headers=HEADERS).status_code == 422
    assert client.post("/api/v1/predict", json=PAYLOAD, headers=HEADERS).status_code == 429


def test_health_ready_missing_model_and_fallback(tmp_path):
    with TestClient(create_app(tmp_path)) as client:
        health = client.get("/health")
        assert health.status_code == 200 and health.json()["process_alive"]
        response = client.get("/ready")
        assert response.status_code == 503
        assert not response.json()["model_loaded"] and not response.json()["model_ready"]
        result = client.post("/api/v1/predict", json=PAYLOAD, headers=HEADERS)
        assert result.status_code == 200
        body = PredictionOutput.model_validate(result.json())
        assert body.metadata.source == "fallback_rule" and body.metadata.degraded
        assert body.prediction.confidence is None


def test_transient_failure_ready_then_recovery(client):
    assert client.get("/ready").status_code == 200
    with patch.object(client.app.state.adapter.model, "predict_proba", side_effect=RuntimeError("private")):
        data = client.post("/api/v1/predict", json=PAYLOAD, headers=HEADERS).json()
        assert data["metadata"]["degraded"]
        assert client.get("/ready").status_code == 503
    assert client.post("/api/v1/predict", json=PAYLOAD, headers=HEADERS).json()["metadata"]["source"] == "model"
    assert client.get("/ready").status_code == 200


def test_model_and_fallback_failure_returns_503(client):
    with patch.object(client.app.state.adapter, "predict", side_effect=RuntimeError("private")):
        with patch("src.api.fallback_decision", side_effect=ValueError("private")):
            response = client.post("/api/v1/predict", json=PAYLOAD, headers=HEADERS)
    assert response.status_code == 503 and "private" not in response.text
    assert response.json()["trace_id"] == response.headers["X-Trace-ID"]


def test_invalid_output_not_returned_as_success(client):
    # Явная подмена результата только в тесте. В основном сценарии настоящий артефакт.
    bad = Decision("TECHNICAL", float("nan"), "IT_SUPPORT", False)
    with patch.object(client.app.state.adapter, "predict", return_value=bad):
        response = client.post("/api/v1/predict", json=PAYLOAD, headers=HEADERS)
    assert response.status_code == 503


@pytest.mark.parametrize("configuration", ["missing", "same_tokens"])
def test_bad_auth_configuration_503(monkeypatch, configuration):
    if configuration == "missing":
        monkeypatch.delenv("APP_DEMO_TOKEN")
    else:
        monkeypatch.setenv("APP_READONLY_TOKEN", "unit-test-only")
    with TestClient(create_app(ROOT)) as client:
        response = client.post("/api/v1/predict", json=PAYLOAD, headers=HEADERS)
        assert response.status_code == 503
        assert client.get("/health").status_code == 200
        assert client.get("/ready").status_code == 503
        assert not client.get("/ready").json()["auth_configured"]


def test_fresh_uuid_each_request(client):
    results = [client.post("/api/v1/predict", json=PAYLOAD, headers=HEADERS).json() for _ in range(2)]
    assert results[0]["trace_id"] != results[1]["trace_id"]
    for body in results:
        assert UUID(body["trace_id"]).version == 4
        assert datetime.fromisoformat(body["metadata"]["timestamp_utc"].replace("Z", "+00:00")).tzinfo


def test_swagger_security_and_statuses(client):
    assert client.get("/docs").status_code == 200
    schema = client.get("/openapi.json").json()
    assert schema["components"]["securitySchemes"]["HTTPBearer"]["scheme"] == "bearer"
    for path in ("/predict", "/api/v1/predict"):
        operation = schema["paths"][path]["post"]
        assert operation["security"] == [{"HTTPBearer": []}]
        assert {"200", "401", "403", "422", "429", "503"} <= set(operation["responses"])
