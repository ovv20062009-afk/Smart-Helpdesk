import json
from pathlib import Path
import shutil
from unittest.mock import patch

from fastapi.testclient import TestClient
import pytest

from src.api import create_app
from src.artifacts import MODEL_VERSION, load_bundle

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def client():
    with TestClient(create_app(ROOT)) as session:
        yield session


def test_health(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["model_version"] == MODEL_VERSION
    assert response.json()["model_loaded"] is True


@pytest.mark.parametrize("text,category", [
    ("Не могу войти в личный кабинет", "TECHNICAL"),
    ("Оплата обучения не отобразилась", "PAYMENT"),
])
def test_trained_predictions(client, text, category):
    response = client.post("/predict", json={"ticket_id": "T-1", "text": text, "channel": "web"})
    assert response.status_code == 200
    result = response.json()
    assert result["category"] == category
    assert 0 <= result["confidence"] <= 1
    assert result["model_version"] == MODEL_VERSION


@pytest.mark.parametrize("payload", [
    {"ticket_id": "T-1", "text": ""},
    {"ticket_id": "T-1", "text": "   "},
    {"ticket_id": "T-1", "text": "!!!123"},
    {"ticket_id": "T-1", "text": "a" * 5001},
    {"ticket_id": "T-1", "text": "Пароль", "channel": "sms"},
    {"ticket_id": "T-1", "text": "Пароль", "password": "extra"},
])
def test_invalid_input_returns_422(client, payload):
    assert client.post("/predict", json=payload).status_code == 422


def test_unknown_words_require_operator(client):
    data = client.post("/predict", json={"ticket_id": "T-2", "text": "абракадабра жужелица"}).json()
    assert data["category"] is None and data["confidence"] is None
    assert data["destination"] == "OPERATOR" and data["manual_review_required"]


def test_low_probability_requires_operator(client):
    response = client.post("/predict", json={"ticket_id": "T-3", "text": "пароль оплата экзамен"})
    data = response.json()
    assert response.status_code == 200
    assert data["confidence"] < 0.8
    assert data["destination"] == "OPERATOR" and data["manual_review_required"]


def test_loads_once_at_start():
    import joblib
    with patch("src.artifacts.joblib.load", wraps=joblib.load) as loader:
        with TestClient(create_app(ROOT)) as client:
            assert loader.call_count == 2
            for _ in range(2):
                assert client.post("/predict", json={"ticket_id": "T-1", "text": "Забыла пароль"}).status_code == 200
            assert loader.call_count == 2


def test_missing_artifact_returns_503(tmp_path):
    with TestClient(create_app(tmp_path)) as client:
        assert client.get("/health").status_code == 503
        assert client.post("/predict", json={"ticket_id": "T-1", "text": "Пароль"}).status_code == 503


def test_bad_checksum_is_rejected(tmp_path):
    for folder in ("artifacts", "models", "src"):
        (tmp_path / folder).mkdir()
    for name in ("artifacts/preprocessor.joblib", "artifacts/manifest.json", "models/model.joblib", "src/preprocessing.py"):
        shutil.copyfile(ROOT / name, tmp_path / name)
    (tmp_path / "models/model.joblib").write_bytes(b"broken")
    with pytest.raises(ValueError, match="Контрольная сумма"):
        load_bundle(tmp_path)


def test_inference_failure_is_not_success(client):
    with patch.object(client.app.state.model, "predict_proba", side_effect=RuntimeError("failed")):
        assert client.post("/predict", json={"ticket_id": "T-1", "text": "Пароль"}).status_code == 500


def test_confident_prediction_selects_department(client):
    response = client.post("/predict", json={"ticket_id": "T-4", "text": "Забыла пароль от аккаунта", "channel": "email"})
    data = response.json()
    assert response.status_code == 200 and data["confidence"] >= 0.8
    assert data["category"] == "TECHNICAL"
    assert data["destination"] == "IT_SUPPORT" and data["manual_review_required"] is False
