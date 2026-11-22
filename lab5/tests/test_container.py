"""Smoke-тесты реального HTTP-сервиса. По умолчанию нужен контейнер на порту 8000."""
import os
import time

import pytest
import requests

BASE_URL = os.environ.get("HELPDESK_URL", "http://127.0.0.1:8000").rstrip("/")


@pytest.fixture(scope="module", autouse=True)
def wait_for_service():
    deadline = time.monotonic() + 60
    last_error = "Сервис не ответил"
    while time.monotonic() < deadline:
        try:
            response = requests.get(BASE_URL + "/health", timeout=3)
            if response.status_code == 200:
                return
            last_error = f"HTTP {response.status_code}: {response.text}"
        except requests.RequestException as error:
            last_error = str(error)
        time.sleep(1)
    pytest.fail("Сервис не готов: " + last_error)


def test_container_health():
    response = requests.get(BASE_URL + "/health", timeout=5)
    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert response.json()["model_version"] == "v1.0.0"


def test_container_predict():
    response = requests.post(BASE_URL + "/predict", timeout=5,
        json={"ticket_id": "T-1", "text": "Не могу войти в личный кабинет", "channel": "web"})
    assert response.status_code == 200
    data = response.json()
    assert data["category"] in ["TECHNICAL", "PAYMENT", "STUDY"]
    assert 0 <= data["confidence"] <= 1
    assert data["model_version"] == "v1.0.0"
    assert data["manual_review_required"] == (data["confidence"] < 0.8)


def test_container_invalid_input():
    response = requests.post(BASE_URL + "/predict", timeout=5, json={"ticket_id": "T-1", "text": ""})
    assert response.status_code == 422


def test_container_manual_review():
    response = requests.post(BASE_URL + "/predict", timeout=5,
        json={"ticket_id": "T-2", "text": "абракадабра жужелица"})
    assert response.status_code == 200
    data = response.json()
    assert data["manual_review_required"] and data["destination"] == "OPERATOR"
