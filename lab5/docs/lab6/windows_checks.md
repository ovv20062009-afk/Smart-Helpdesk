# Проверки ЛР 6 на Windows

Результаты команд, выполненных на компьютере с Windows, Python 3.12.2 и Docker Desktop. Дата проверки: 22.11.2026.

| Проверка | Результат |
|---|---|
| pytest -q | 41 passed, 1 warning за 4.85 с |
| record_docker.py | 5 passed за 0.61 с |
| Резервный контейнер, tests/test_container.py | 5 passed за 0.68 с |
| docker inspect smart-helpdesk-lab6 | healthy |
| check_json_logs.py для fallback_logs.jsonl | valid_json_lines: 13, requests: 7 |
| Ручное открытие /docs | Страница открылась |

Предупреждение pytest касается устаревающего имени BlockingPortal в зависимости Starlette. Тесты прошли.

Образ: `smart-helpdesk:v1.4.0`.

ID: `sha256:b5005941579bd645c24c73bff5a63ee1160ffad03534bbaf3662f2faf5382e73`.

Размер: 156912872 байта, 149.64 MiB. Суммарный размер включённых файлов по record_docker.py: 47728 байт.

Обычный контейнер: smart-helpdesk-lab6, порт 8000. Резервный: smart-helpdesk-lab6-fallback, порт 8001, HELPDESK_DISABLE_MODEL=1.

Ответ резервного сценария, полученный через curl с HTTP 200:

```json
{
  "trace_id": "151f7771-1fcd-4f5e-aecc-f00a73db2460",
  "ticket_id": "T-FALLBACK",
  "category": "TECHNICAL",
  "confidence": null,
  "destination": "IT_SUPPORT",
  "manual_review_required": false,
  "model_version": "v1.4.0",
  "preprocessor_version": "lab4-tfidf-v1",
  "source": "fallback_rule",
  "latency_ms": 3.804,
  "matched_words": ["войти", "пароль"]
}
```

Тот же trace_id указан в заголовке X-Trace-ID. Скрипт проверки нашёл его в сохранённом журнале. Проверка журнала выполнена перед дополнительными пятью тестами резервного контейнера, поэтому количество записей относится к тому моменту.

При записи docker_result.json healthcheck ещё показывал starting. После завершения запуска отдельная команда docker inspect показала healthy.

GitHub Actions в эту локальную проверку не входит. Его результат нужно проверить после отправки ветки.
