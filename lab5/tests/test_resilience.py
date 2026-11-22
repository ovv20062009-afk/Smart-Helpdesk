from pathlib import Path
from unittest.mock import patch
from uuid import UUID

from fastapi.testclient import TestClient
import numpy as np
import pytest

from src.api import create_app

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize("failure", ["missing_model", "model_error", "preprocessing_error", "nan_output"])
def test_runtime_failure_uses_rule(failure):
    with TestClient(create_app(ROOT), headers={"Authorization": "Bearer unit-test-only"}) as client:
        model = client.app.state.adapter.model
        preprocessor = client.app.state.adapter.preprocessor
        if failure == "missing_model":
            client.app.state.adapter.model = None
            context = patch.object(preprocessor, "transform", wraps=preprocessor.transform)
        elif failure == "model_error":
            context = patch.object(model, "predict_proba", side_effect=RuntimeError("secret internal data"))
        elif failure == "preprocessing_error":
            context = patch.object(preprocessor, "transform", side_effect=ValueError("secret"))
        else:
            context = patch.object(model, "predict_proba", return_value=np.array([[np.nan, 0.1, 0.9]]))
        with context:
            response = client.post("/predict", json={"ticket_id": "T-6", "text": "Не могу войти, забыла пароль"})
        assert response.status_code == 200
        data = response.json()
        assert data["source"] == "fallback_rule"
        assert data["category"] == "TECHNICAL" and data["destination"] == "IT_SUPPORT"
        assert data["confidence"] is None
        assert not data["manual_review_required"]
        assert UUID(data["trace_id"]).version == 4
        assert response.headers["X-Trace-ID"] == data["trace_id"]
        assert "secret" not in response.text


def test_missing_artifacts_still_allow_manual_queue(tmp_path):
    with TestClient(create_app(tmp_path), headers={"Authorization": "Bearer unit-test-only"}) as client:
        assert client.get("/health").json()["status"] == "degraded"
        result = client.post("/predict", json={"ticket_id": "T-7", "text": "Пароль и оплата"}).json()
        assert result["source"] == "fallback_rule" and result["destination"] == "OPERATOR"
        assert result["manual_review_required"] and result["category"] is None
        assert result["confidence"] is None


def test_invalid_input_does_not_enter_fallback(tmp_path):
    with TestClient(create_app(tmp_path), headers={"Authorization": "Bearer unit-test-only"}) as client:
        with patch("src.api.fallback_decision") as fallback:
            response = client.post("/predict", json={"ticket_id": "T-1", "text": ""})
            assert response.status_code == 422
            fallback.assert_not_called()
            assert UUID(response.headers["X-Trace-ID"]).version == 4


def test_model_can_recover_after_transient_error():
    with TestClient(create_app(ROOT), headers={"Authorization": "Bearer unit-test-only"}) as client:
        with patch.object(client.app.state.adapter.model, "predict_proba", side_effect=RuntimeError("failed")):
            assert client.post("/predict", json={"ticket_id": "T-1", "text": "Пароль"}).json()["source"] == "fallback_rule"
        assert client.get("/health").json()["status"] == "degraded"
        assert client.post("/predict", json={"ticket_id": "T-2", "text": "Пароль"}).json()["source"] == "model"
        assert client.get("/health").json()["status"] == "ok"


def test_demonstration_can_disable_model(monkeypatch):
    monkeypatch.setenv("HELPDESK_DISABLE_MODEL", "1")
    with patch("src.model_adapter.load_bundle") as loader:
        with TestClient(create_app(ROOT), headers={"Authorization": "Bearer unit-test-only"}) as client:
            response = client.post("/predict", json={"ticket_id": "T-8", "text": "Оплата квитанция"})
            assert response.status_code == 200
            assert response.json()["source"] == "fallback_rule"
            loader.assert_not_called()
