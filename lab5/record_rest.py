"""Записывает фактический протокол HTTP-проверок. Токены не сохраняет."""
import argparse
import json
import subprocess
import sys
import os
from pathlib import Path

import requests

from configure_local import local_environment
from src.schemas import PredictionOutput

ROOT = Path(__file__).resolve().parent
PAYLOAD = {"ticket_id": "T-LAB7", "text": "Не могу войти, забыла пароль", "channel": "web"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fallback", action="store_true", help="Проверить контейнер с отключённой моделью на порту 8001")
    args = parser.parse_args()
    env = local_environment()
    if args.fallback:
        url = os.environ.get("HELPDESK_URL", "http://127.0.0.1:8001").rstrip("/")
        env.update(HELPDESK_URL=url, HELPDESK_EXPECT_SOURCE="fallback_rule")
        output = ROOT / "docs/lab7"
        output.mkdir(parents=True, exist_ok=True)
        result = subprocess.run([sys.executable, "-m", "pytest", "-q", "tests/test_container.py"],
                                cwd=ROOT, env=env, capture_output=True, text=True, encoding="utf-8", errors="replace")
        (output / "fallback_container_tests.txt").write_text(result.stdout + result.stderr, encoding="utf-8")
        print(result.stdout)
        if result.returncode:
            raise SystemExit(result.returncode)
        response = requests.post(url + "/api/v1/predict", json=PAYLOAD,
                                headers={"Authorization": "Bearer " + env["APP_DEMO_TOKEN"]}, timeout=10)
        assert response.status_code == 200
        body = PredictionOutput.model_validate(response.json())
        assert body.metadata.source == "fallback_rule" and body.metadata.degraded
        assert body.prediction.confidence is None
        assert requests.get(url + "/ready", timeout=10).status_code == 503
        (output / "fallback_response.json").write_text(response.text + "\n", encoding="utf-8")
        print(response.text)
        return
    url = os.environ.get("HELPDESK_URL", "http://127.0.0.1:8000").rstrip("/")
    headers = {"Authorization": "Bearer " + env["APP_DEMO_TOKEN"]}
    output = ROOT / "docs/lab7"
    output.mkdir(parents=True, exist_ok=True)
    results = []

    def check(name, response, expected):
        row = {"check": name, "expected": expected, "actual": response.status_code,
               "trace_id": response.headers.get("X-Trace-ID")}
        if response.status_code == 429:
            row["retry_after"] = response.headers.get("Retry-After")
            assert int(row["retry_after"]) > 0
        results.append(row)
        assert response.status_code == expected, (name, expected, response.status_code)
        assert row["trace_id"], name
        return response

    check("health", requests.get(url + "/health", timeout=10), 200)
    check("ready", requests.get(url + "/ready", timeout=10), 200)
    response = check("real_model", requests.post(url + "/api/v1/predict", json=PAYLOAD, headers=headers, timeout=10), 200)
    body = PredictionOutput.model_validate(response.json())
    assert body.metadata.source == "model" and not body.metadata.degraded
    (output / "real_model_response.json").write_text(response.text + "\n", encoding="utf-8")
    check("no_token", requests.post(url + "/api/v1/predict", json=PAYLOAD, timeout=10), 401)
    check("wrong_token", requests.post(url + "/api/v1/predict", json=PAYLOAD,
          headers={"Authorization": "Bearer intentionally-wrong"}, timeout=10), 401)
    check("forbidden", requests.post(url + "/api/v1/predict", json=PAYLOAD,
          headers={"Authorization": "Bearer " + env["APP_READONLY_TOKEN"]}, timeout=10), 403)
    check("invalid_input", requests.post(url + "/api/v1/predict", json={**PAYLOAD, "channel": "sms"}, headers=headers, timeout=10), 422)
    # Проверяем настоящую квоту до первого 429. Реального ожидания минуты нет.
    for _ in range(61):
        response = requests.post(url + "/api/v1/predict", json=PAYLOAD, headers=headers, timeout=10)
        if response.status_code == 429:
            check("quota_exhausted", response, 429)
            break
        assert response.status_code == 200
    else:
        raise AssertionError("Квота не сработала")
    check("health_after_quota", requests.get(url + "/health", timeout=10), 200)
    (output / "http_protocol.json").write_text(json.dumps(results, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(results, ensure_ascii=False, indent=2))
    print("Квота исчерпана намеренно. Дождитесь Retry-After или перезапустите учебный контейнер.")


if __name__ == "__main__":
    main()
