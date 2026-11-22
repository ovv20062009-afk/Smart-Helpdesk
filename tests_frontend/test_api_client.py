import pytest
import requests

from frontend.api_client import ApiClientError, request_prediction


class Response:
    def __init__(self, code=200, body=None, headers=None):
        self.status_code, self.body, self.headers = code, body, headers or {}

    def json(self):
        return self.body


def test_request_headers_timeout_and_no_redirect(monkeypatch, body, payload):
    calls = []
    def post(*args, **kwargs):
        calls.append((args, kwargs))
        return Response(body=body, headers={"X-Trace-ID": body["trace_id"]})
    monkeypatch.setattr(requests, "post", post)
    result = request_prediction("http://test/", "unit-test-secret", payload)
    assert result.metadata.source == "model"
    assert len(calls) == 1
    args, kwargs = calls[0]
    assert args[0] == "http://test/api/v1/predict"
    assert kwargs["headers"] == {"Authorization": "Bearer unit-test-secret"}
    assert kwargs["json"] == payload
    assert kwargs["timeout"] == (3, 10) and kwargs["allow_redirects"] is False
    assert "unit-test-secret" not in result.model_dump_json()


@pytest.mark.parametrize("code", [401, 403, 422, 429, 503, 500, 302])
def test_status_messages_no_internal_body(monkeypatch, payload, code):
    monkeypatch.setattr(requests, "post", lambda *a, **k: Response(code, body={"detail": "PRIVATE"},
                      headers={"Retry-After": "7", "X-Trace-ID": "2ff952d6-ca63-4b28-b254-8e90fbee96f0"}))
    with pytest.raises(ApiClientError) as error:
        request_prediction("http://test", "unit-test-secret", payload)
    assert error.value.code == str(code)
    assert error.value.retry_after == ("7" if code == 429 else None)
    assert "PRIVATE" not in str(error.value)


@pytest.mark.parametrize("retry", ["7", "Sun, 22 Nov 2026 10:00:00 GMT"])
def test_retry_after_is_hint_not_auto_retry(monkeypatch, payload, retry):
    calls = []
    def post(*a, **k):
        calls.append(1)
        return Response(429, headers={"Retry-After": retry})
    monkeypatch.setattr(requests, "post", post)
    with pytest.raises(ApiClientError) as error:
        request_prediction("http://test", "secret", payload)
    assert error.value.retry_after == retry
    assert len(calls) == 1


@pytest.mark.parametrize("exception,code", [(requests.Timeout, "timeout"), (requests.ConnectionError, "connection"),
                                           (requests.RequestException, "network")])
def test_network_errors_are_safe(monkeypatch, payload, exception, code):
    def fail(*a, **k):
        raise exception("PRIVATE TOKEN INTERNAL")
    monkeypatch.setattr(requests, "post", fail)
    with pytest.raises(ApiClientError) as error:
        request_prediction("http://test", "secret", payload)
    assert error.value.code == code
    assert "PRIVATE" not in error.value.message and "TOKEN" not in error.value.message


def test_invalid_json_is_contract_error(monkeypatch, payload):
    class InvalidJSON(Response):
        def json(self):
            raise ValueError("PRIVATE")
    monkeypatch.setattr(requests, "post", lambda *a, **k: InvalidJSON())
    with pytest.raises(ApiClientError) as error:
        request_prediction("http://test", "secret", payload)
    assert error.value.code == "contract"


@pytest.mark.parametrize("value", [{"unexpected": True}, None, [], "text"])
def test_incomplete_schema(monkeypatch, payload, value):
    monkeypatch.setattr(requests, "post", lambda *a, **k: Response(body=value))
    with pytest.raises(ApiClientError) as error:
        request_prediction("http://test", "secret", payload)
    assert error.value.code == "contract"


def test_other_ticket_rejected(monkeypatch, body, payload):
    body["ticket_id"] = "T-OTHER"
    monkeypatch.setattr(requests, "post", lambda *a, **k: Response(body=body))
    with pytest.raises(ApiClientError) as error:
        request_prediction("http://test", "secret", payload)
    assert error.value.code == "contract"


def test_other_trace_header_rejected(monkeypatch, body, payload):
    monkeypatch.setattr(requests, "post", lambda *a, **k: Response(body=body, headers={"X-Trace-ID": "invalid"}))
    with pytest.raises(ApiClientError) as error:
        request_prediction("http://test", "secret", payload)
    assert error.value.code == "contract"


def test_fallback_accepted(monkeypatch, fallback, payload):
    monkeypatch.setattr(requests, "post", lambda *a, **k: Response(body=fallback))
    result = request_prediction("http://test", "secret", payload)
    assert result.metadata.degraded and result.prediction.confidence is None


def test_missing_token_does_not_call_http(monkeypatch, payload):
    def fail(*a, **k):
        pytest.fail("HTTP не должен вызываться")
    monkeypatch.setattr(requests, "post", fail)
    with pytest.raises(ApiClientError) as error:
        request_prediction("http://test", "", payload)
    assert error.value.code == "config"


@pytest.mark.parametrize("url", ["bad", "ftp://test", "http://user:password@test", "http://test?token=secret"])
def test_bad_configuration(url, payload):
    with pytest.raises(ApiClientError) as error:
        request_prediction(url, "secret", payload)
    assert error.value.code == "config"


def test_invalid_input_not_sent(monkeypatch, payload):
    def fail(*a, **k):
        pytest.fail("Неверный ввод не должен отправляться")
    monkeypatch.setattr(requests, "post", fail)
    with pytest.raises(ApiClientError) as error:
        request_prediction("http://test", "secret", {**payload, "ticket_id": "../"})
    assert error.value.code == "input"
