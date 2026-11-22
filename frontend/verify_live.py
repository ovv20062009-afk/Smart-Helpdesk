"""Воспроизводимая проверка формы AppTest с настоящими HTTP-запросами."""
import csv
import io
import json
import os
from pathlib import Path
import socket
import time

import requests
from streamlit.testing.v1 import AppTest

from frontend.history import export_csv
from frontend.run_ui import settings

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "frontend/app.py"
OUTPUT = ROOT / "docs/lab8"


def wait_for_api(url, ready_code):
    deadline = time.monotonic() + 60
    while time.monotonic() < deadline:
        try:
            if requests.get(url + "/ready", timeout=(3, 3)).status_code == ready_code:
                return
        except requests.RequestException:
            pass
        time.sleep(1)
    raise SystemExit("API не готов к проверке. Посмотрите /health, /ready и состояние контейнера.")


def send(app, ticket_id):
    app.text_input[0].set_value(ticket_id)
    app.button[0].click().run()
    assert not app.exception, "Ошибка приложения"
    return app.session_state["current"]


def main():
    env = settings()
    main_url = env["API_URL"].rstrip("/")
    fallback_url = os.getenv("FALLBACK_API_URL", "http://127.0.0.1:8001").rstrip("/")
    token = env["API_TOKEN"]
    wait_for_api(main_url, 200)
    wait_for_api(fallback_url, 503)
    OUTPUT.mkdir(parents=True, exist_ok=True)
    previous = {key: os.environ.get(key) for key in ("API_URL", "API_TOKEN")}
    checks = []
    try:
        os.environ.update(API_URL=main_url, API_TOKEN=token)
        app = AppTest.from_file(APP, default_timeout=20).run()
        first = send(app, "UI-REAL-1")["result"]
        assert first["metadata"]["source"] == "model" and not first["metadata"]["degraded"]
        second = send(app, "UI-REAL-2")["result"]
        assert first["trace_id"] != second["trace_id"]
        assert second["ticket_id"] == "UI-REAL-2"
        checks.append({"scenario": "Форма с настоящей моделью и новый запрос", "method": "AppTest и реальный HTTP", "result": "passed", "trace_id": second["trace_id"]})
        (OUTPUT / "real_ui_response.json").write_text(json.dumps(second, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

        os.environ["API_TOKEN"] = "intentionally-wrong-ui-test"
        current = send(app, "UI-401")
        assert current["code"] == "401" and not app.metric
        checks.append({"scenario": "Ошибка доступа после успешного запроса", "method": "Реальный HTTP с неверным токеном", "result": "passed"})
        os.environ["API_TOKEN"] = token

        # Сокет занят, но не слушает: управляемый реальный отказ соединения.
        with socket.socket() as offline:
            offline.bind(("127.0.0.1", 0))
            os.environ["API_URL"] = "http://127.0.0.1:" + str(offline.getsockname()[1])
            current = send(app, "UI-OFFLINE")
            assert current["code"] == "connection" and not app.metric
        checks.append({"scenario": "Недоступный сервер", "method": "Реальное соединение с локальным портом без слушателя", "result": "passed"})

        os.environ["API_URL"] = fallback_url
        current = send(app, "UI-FALLBACK")
        fallback = current["result"]
        assert fallback["metadata"]["source"] == "fallback_rule" and fallback["metadata"]["degraded"]
        assert fallback["prediction"]["confidence"] is None and not app.metric
        assert any("Резервный режим" in warning.value for warning in app.warning)
        (OUTPUT / "fallback_ui_response.json").write_text(json.dumps(fallback, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        checks.append({"scenario": "Резервный режим", "method": "Реальный HTTP к API с HELPDESK_DISABLE_MODEL=1", "result": "passed", "trace_id": fallback["trace_id"]})

        os.environ["API_URL"] = main_url
        payload = {"ticket_id": "UI-QUOTA", "text": "Не могу войти, забыла пароль", "channel": "web"}
        for _ in range(61):
            response = requests.post(main_url + "/api/v1/predict", json=payload,
                headers={"Authorization": "Bearer " + token}, timeout=(3, 10), allow_redirects=False)
            if response.status_code == 429:
                break
            assert response.status_code == 200
        else:
            raise AssertionError("Квота не сработала")
        current = send(app, "UI-429")
        assert current["code"] == "429" and current["retry_after"] and not app.metric
        checks.append({"scenario": "Квота и Retry-After в форме", "method": "Реальный HTTP, намеренное заполнение окна", "result": "passed", "retry_after": current["retry_after"]})

        history = app.session_state["history"]
        data = export_csv(history)
        parsed = list(csv.DictReader(io.StringIO(data.decode("utf-8-sig"))))
        assert len(parsed) == 6 and parsed[-1]["error_code"] == "429"
        assert parsed[-1]["confidence"] == "" and parsed[4]["source"] == "fallback_rule"
        assert token not in data.decode("utf-8-sig") and "Authorization" not in parsed[0]
        (OUTPUT / "ui_history.csv").write_bytes(data)
        checks.append({"scenario": "История и CSV", "method": "Шесть реальных попыток формы, чтение CSV через csv.DictReader", "result": "passed", "rows": len(parsed)})
        (OUTPUT / "live_protocol.json").write_text(json.dumps(checks, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    finally:
        for key, value in previous.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
    print(json.dumps(checks, ensure_ascii=False, indent=2))
    print("Проверка завершена. Квота исчерпана намеренно; дождитесь Retry-After либо перезапустите учебный API.")


if __name__ == "__main__":
    main()
