"""Сетевые проверки реального сервиса с рабочим артефактом или явным Fallback."""
import os
import time
from uuid import UUID

import pytest
import requests

from src.schemas import PredictionOutput

BASE_URL = os.environ.get("HELPDESK_URL", "http://127.0.0.1:8000").rstrip("/")
EXPECTED_SOURCE = os.environ.get("HELPDESK_EXPECT_SOURCE", "model")
TOKEN = os.environ.get("APP_DEMO_TOKEN", "")
READONLY_TOKEN = os.environ.get("APP_READONLY_TOKEN", "")
HEADERS = {"Authorization": "Bearer " + TOKEN}
PAYLOAD = {"ticket_id": "T-7", "text": "Не могу войти, забыла пароль", "channel": "web"}


@pytest.fixture(scope="module", autouse=True)
def wait_for_service():
    assert TOKEN, "APP_DEMO_TOKEN не задан для проверки"
    deadline = time.monotonic() + 60
    while time.monotonic() < deadline:
        try:
            if requests.get(BASE_URL + "/health", timeout=3).status_code == 200:
                return
        except requests.RequestException:
            pass
        time.sleep(1)
    pytest.fail("Сервис не ответил на /health")


def test_container_health_and_ready():
    health = requests.get(BASE_URL + "/health", timeout=5)
    assert health.status_code == 200 and health.json()["process_alive"]
    ready = requests.get(BASE_URL + "/ready", timeout=5)
    assert ready.status_code == (200 if EXPECTED_SOURCE == "model" else 503)
    assert ready.json()["model_ready"] == (EXPECTED_SOURCE == "model")
    assert UUID(health.headers["X-Trace-ID"]).version == 4


def test_container_predict():
    response = requests.post(BASE_URL + "/api/v1/predict", json=PAYLOAD, headers=HEADERS, timeout=5)
    assert response.status_code == 200
    body = PredictionOutput.model_validate(response.json())
    assert body.prediction.category == "TECHNICAL"
    assert body.metadata.source == EXPECTED_SOURCE
    assert body.metadata.degraded == (EXPECTED_SOURCE == "fallback_rule")
    assert body.metadata.model_version == "v1.4.0"
    assert response.headers["X-Trace-ID"] == str(body.trace_id)
    if EXPECTED_SOURCE == "model":
        assert 0 <= body.prediction.confidence <= 1
    else:
        assert body.prediction.confidence is None
        assert body.prediction.destination == "IT_SUPPORT"


def test_container_invalid_input():
    response = requests.post(BASE_URL + "/api/v1/predict", json={**PAYLOAD, "text": ""}, headers=HEADERS, timeout=5)
    assert response.status_code == 422
    assert response.json()["trace_id"] == response.headers["X-Trace-ID"]


def test_container_manual_review():
    response = requests.post(BASE_URL + "/api/v1/predict", json={**PAYLOAD, "text": "абракадабра жужелица"}, headers=HEADERS, timeout=5)
    assert response.status_code == 200
    body = PredictionOutput.model_validate(response.json())
    assert body.prediction.manual_review_required and body.prediction.destination == "OPERATOR"
    assert body.prediction.confidence is None


def test_container_unauthorized_and_forbidden():
    for path in ("/api/v1/predict", "/predict"):
        response = requests.post(BASE_URL + path, json=PAYLOAD, timeout=5)
        assert response.status_code == 401 and response.headers["WWW-Authenticate"] == "Bearer"
    assert READONLY_TOKEN, "APP_READONLY_TOKEN не задан для проверки 403"
    response = requests.post(BASE_URL + "/api/v1/predict", json=PAYLOAD,
                            headers={"Authorization": "Bearer " + READONLY_TOKEN}, timeout=5)
    assert response.status_code == 403


def test_swagger_and_schema():
    assert requests.get(BASE_URL + "/docs", timeout=5).status_code == 200
    schema = requests.get(BASE_URL + "/openapi.json", timeout=5).json()
    assert schema["paths"]["/api/v1/predict"]["post"]["security"] == [{"HTTPBearer": []}]
    assert schema["components"]["schemas"]["PredictionOutput"]["properties"]["metadata"]["description"]
