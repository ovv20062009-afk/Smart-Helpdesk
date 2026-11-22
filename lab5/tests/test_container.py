"""Smoke-тесты настоящего сервиса: обычный режим и Fallback-контейнер."""
import os
import time
from uuid import UUID

import pytest
import requests

BASE_URL = os.environ.get("HELPDESK_URL", "http://127.0.0.1:8000").rstrip("/")
EXPECTED_SOURCE = os.environ.get("HELPDESK_EXPECT_SOURCE", "model")


@pytest.fixture(scope="module", autouse=True)
def wait_for_service():
    deadline = time.monotonic() + 60
    last_error = "Сервис не ответил"
    while time.monotonic() < deadline:
        try:
            response = requests.get(BASE_URL + "/health", timeout=3)
            if response.status_code == 200:
                return
            last_error = f"HTTP {response.status_code}"
        except requests.RequestException as error:
            last_error = type(error).__name__
        time.sleep(1)
    pytest.fail("Сервис не готов: " + last_error)


def test_container_health():
    response = requests.get(BASE_URL + "/health", timeout=5)
    assert response.status_code == 200
    assert response.json()["status"] == ("ok" if EXPECTED_SOURCE == "model" else "degraded")
    assert response.json()["model_version"] == "v1.4.0"
    assert UUID(response.headers["X-Trace-ID"]).version == 4


def test_container_predict():
    response = requests.post(BASE_URL + "/predict", timeout=5,
        json={"ticket_id": "T-1", "text": "Не могу войти, забыла пароль", "channel": "web"})
    assert response.status_code == 200
    data = response.json()
    assert data["category"] == "TECHNICAL" and data["source"] == EXPECTED_SOURCE
    assert data["model_version"] == "v1.4.0"
    assert response.headers["X-Trace-ID"] == data["trace_id"]
    assert data["latency_ms"] >= 0
    if EXPECTED_SOURCE == "model":
        assert 0 <= data["confidence"] <= 1
        assert data["manual_review_required"] == (data["confidence"] < 0.8)
    else:
        assert data["confidence"] is None
        assert data["matched_words"] == ["войти", "пароль"]
        assert data["destination"] == "IT_SUPPORT" and not data["manual_review_required"]


def test_container_invalid_input():
    response = requests.post(BASE_URL + "/predict", timeout=5, json={"ticket_id": "T-1", "text": ""})
    assert response.status_code == 422
    assert UUID(response.headers["X-Trace-ID"]).version == 4


def test_container_manual_review():
    response = requests.post(BASE_URL + "/predict", timeout=5,
        json={"ticket_id": "T-2", "text": "абракадабра жужелица"})
    assert response.status_code == 200
    data = response.json()
    assert data["manual_review_required"] and data["destination"] == "OPERATOR"
    assert data["confidence"] is None and data["source"] == EXPECTED_SOURCE


def test_swagger_and_schema():
    assert requests.get(BASE_URL + "/docs", timeout=5).status_code == 200
    schema = requests.get(BASE_URL + "/openapi.json", timeout=5).json()
    assert schema["info"]["version"] == "v1.4.0"
    assert schema["components"]["schemas"]["PredictionResult"]["properties"]["source"]["description"]
