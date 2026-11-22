from pathlib import Path
from unittest.mock import patch

from streamlit.testing.v1 import AppTest

from frontend.api_client import ApiClientError
from frontend.response_validation import ApiResponse

APP = Path(__file__).resolve().parents[1] / "frontend/app.py"


def submit(app):
    return app.button[0].click().run()


def test_form_waits_for_submit(monkeypatch, body):
    monkeypatch.setenv("API_TOKEN", "UI_PRIVATE_TOKEN")
    with patch("frontend.api_client.request_prediction") as client:
        app = AppTest.from_file(APP).run()
        client.assert_not_called()
    assert not app.exception
    assert len(app.session_state["history"]) == 0


def test_success_then_error_does_not_show_old_score(monkeypatch, body):
    monkeypatch.setenv("API_TOKEN", "UI_PRIVATE_TOKEN")
    with patch("frontend.api_client.request_prediction", return_value=ApiResponse.model_validate(body)):
        app = AppTest.from_file(APP).run()
        submit(app)
    assert not app.exception
    assert len(app.metric) == 1 and app.metric[0].value == "0.720"
    assert len(app.session_state["history"]) == 1
    with patch("frontend.api_client.request_prediction", side_effect=ApiClientError("timeout", "Время ожидания истекло")):
        app.text_input[0].set_value("T-NEW")
        submit(app)
    assert not app.exception and len(app.metric) == 0
    assert app.error[0].value == "Время ожидания истекло"
    history = app.session_state["history"]
    assert len(history) == 2 and history[-1]["confidence"] is None
    assert history[-1]["ticket_id"] == "T-NEW" and history[-1]["error_code"] == "timeout"
    assert "UI_PRIVATE_TOKEN" not in str(history)


def test_fallback_is_visible_without_score(monkeypatch, fallback):
    monkeypatch.setenv("API_TOKEN", "UI_PRIVATE_TOKEN")
    with patch("frontend.api_client.request_prediction", return_value=ApiResponse.model_validate(fallback)):
        app = AppTest.from_file(APP).run()
        submit(app)
    assert not app.exception
    assert len(app.metric) == 0
    assert any("Резервный режим" in warning.value for warning in app.warning)
    assert app.session_state["history"][-1]["status"] == "degraded"


def test_invalid_form_never_calls_api_and_clear_works():
    with patch("frontend.api_client.request_prediction") as client:
        app = AppTest.from_file(APP).run()
        app.text_input[0].set_value("../")
        submit(app)
        client.assert_not_called()
    assert not app.exception and app.error
    assert app.session_state["history"][-1]["error_code"] == "input"
    app.button[1].click().run()
    assert not app.exception and not app.session_state["history"]
    assert app.session_state["current"] is None


def test_429_hint_does_not_show_result():
    with patch("frontend.api_client.request_prediction", side_effect=ApiClientError("429", "Лимит исчерпан", retry_after="7")):
        app = AppTest.from_file(APP).run()
        submit(app)
    assert not app.exception and not app.metric
    assert any("Retry-After: 7" in item.value for item in app.text)
