from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
import io
import json
import logging
from pathlib import Path
import sys
from uuid import UUID

from fastapi.testclient import TestClient

from src.api import create_app
from src.logger import JSONFormatter, get_json_logger

ROOT = Path(__file__).resolve().parents[1]


@contextmanager
def captured_logs():
    logger = get_json_logger()
    previous = logger.handlers[:]
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(JSONFormatter())
    logger.handlers = [handler]
    try:
        yield stream
    finally:
        logger.handlers = previous
        handler.close()


def test_stdout_and_no_duplicate_handlers():
    logger = get_json_logger("stdout_test")
    assert logger is get_json_logger("stdout_test")
    assert len(logger.handlers) == 1
    assert logger.handlers[0].stream is sys.stdout
    assert not logger.propagate


def test_trace_matches_response_header_and_json_log():
    with captured_logs() as stream:
        with TestClient(create_app(ROOT)) as client:
            response = client.post("/predict", json={"ticket_id": "T-1", "text": "Не могу войти, забыла пароль"})
    data = response.json()
    assert response.headers["X-Trace-ID"] == data["trace_id"]
    assert UUID(data["trace_id"]).version == 4
    records = [json.loads(line) for line in stream.getvalue().splitlines()]
    record = next(item for item in records if item.get("trace_id") == data["trace_id"] and item["message"] == "request_complete")
    assert record["source"] == data["source"]
    assert record["latency_ms"] == data["latency_ms"]
    assert record["status_code"] == 200


def test_no_secret_text_headers_or_validation_input_in_logs(tmp_path):
    with captured_logs() as stream:
        with TestClient(create_app(tmp_path)) as client:
            client.post("/predict?token=QUERY_SECRET", headers={"Authorization": "Bearer HEADER_SECRET"},
                        json={"ticket_id": "T-2", "text": "Пароль TEXT_SECRET"})
            response = client.post("/predict", json={"ticket_id": "T-2", "text": "", "password": "EXTRA_SECRET"})
    logs = stream.getvalue()
    for secret in ("QUERY_SECRET", "HEADER_SECRET", "TEXT_SECRET", "EXTRA_SECRET"):
        assert secret not in logs
    assert "EXTRA_SECRET" not in response.text
    for line in logs.splitlines():
        json.loads(line)


def test_formatter_keeps_one_line_and_filters_extra_fields():
    record = logging.LogRecord("example", logging.INFO, "", 0, "line1\nline2", (), None)
    record.extra_data = {"password": "SECRET", "trace_id": "safe", "text": "SECRET"}
    formatted = JSONFormatter().format(record)
    assert "\n" not in formatted
    assert json.loads(formatted)["message"] == "line1\nline2"
    assert "SECRET" not in formatted


def test_parallel_requests_have_distinct_traces():
    with captured_logs() as stream:
        with TestClient(create_app(ROOT)) as client:
            def call(i):
                return client.post("/predict", json={"ticket_id": f"T-{i}", "text": "Пароль"})
            with ThreadPoolExecutor(max_workers=4) as executor:
                responses = list(executor.map(call, range(4)))
    ids = [response.json()["trace_id"] for response in responses]
    assert len(set(ids)) == 4
    for response in responses:
        assert response.headers["X-Trace-ID"] == response.json()["trace_id"]
    records = [json.loads(line) for line in stream.getvalue().splitlines()]
    for trace_id in ids:
        assert sum(item.get("trace_id") == trace_id and item["message"] == "request_complete" for item in records) == 1


def test_swagger_fields_have_descriptions():
    with TestClient(create_app(ROOT)) as client:
        assert client.get("/docs").status_code == 200
        schema = client.get("/openapi.json").json()
    for name in ("PredictionRequest", "PredictionResult"):
        for field in schema["components"]["schemas"][name]["properties"].values():
            assert field.get("description")


def test_formatter_is_one_json_line_and_filters_fields():
    record = logging.LogRecord("safe", logging.INFO, "", 0, "one\ntwo", (), None)
    record.extra_data = {"text": "private-text", "Authorization": "private-token", "source": "model"}
    result = JSONFormatter().format(record)
    assert "\n" not in result
    assert "private-text" not in result and "private-token" not in result
    assert json.loads(result)["source"] == "model"


def test_concurrent_requests_keep_separate_traces():
    with captured_logs() as stream:
        with TestClient(create_app(ROOT)) as client:
            def send(index):
                return client.post("/predict", json={"ticket_id": f"T-{index}", "text": "Пароль"})
            with ThreadPoolExecutor(max_workers=4) as pool:
                responses = list(pool.map(send, range(4)))
    ids = {response.json()["trace_id"] for response in responses}
    assert len(ids) == 4
    records = [json.loads(line) for line in stream.getvalue().splitlines()]
    for response in responses:
        result = response.json()
        assert result["trace_id"] == response.headers["X-Trace-ID"]
        linked = [item for item in records if item.get("trace_id") == result["trace_id"]]
        assert len(linked) == 1
        assert linked[0]["ticket_id"] == result["ticket_id"]
