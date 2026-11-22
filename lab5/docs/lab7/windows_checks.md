# Проверки ЛР 7 на Windows

Дата: 22.11.2026. Результаты собраны по выводу команд и фактическим ответам Swagger. Токены не включены.

| Проверка | Результат |
|---|---|
| pytest -q | 87 passed, 1 warning за 9.95 с |
| Сборка Docker | Успешна, переданный контекст 58.01 kB |
| Образ | smart-helpdesk:v1.4.0, 156915589 байт, 149.65 MiB |
| Основной контейнер | smart-helpdesk-lab7, running=true, порт 8000, healthy |
| record_docker.py | smoke_tests=passed, included_files_bytes=58640 |
| Нет токена | 401 |
| Неверный токен | 401 |
| Недостаточно прав | 403 |
| Неверный вход | 422 |
| Квота | 429, Retry-After: 16 |
| /health после исчерпания квоты | 200 |
| Резервный контейнер | 6 passed за 1.03 с |
| Проверка fallback_logs.jsonl | valid_json_lines=27, requests=19 |
| Trace ID резервного ответа | 7a718068-b566-4e3d-9cd7-ee7d725de270 найден в журнале |
| Swagger, POST /api/v1/predict | 200, source=model, degraded=false |
| Swagger, GET /ready | 200, status=ready, модель и препроцессор загружены, доступ настроен |

ID образа: `sha256:a1bdcf8cd4e58df0d0f8d1805d90fe25eb6b795e38b79ad6cbbdd1526006338b`.

Основной ответ сохранён в swagger_predict_response.json. Оценка 0.7278679283013162 меньше порога 0.8, поэтому маршрут OPERATOR и ручная проверка ожидаемы. Идентификатор в теле совпал с X-Trace-ID.

Результат /ready сохранён в swagger_ready_response.json. Его идентификатор также совпал с X-Trace-ID.

Резервный ответ: TECHNICAL, IT_SUPPORT, confidence=null, manual_review_required=false, source=fallback_rule, degraded=true, latency_ms=0.37. Совпадения: «войти», «пароль».

Полные журналы и протоколы записаны скриптами на компьютере. В эту сводку включены только фактически показанные результаты. Число строк журнала относится к моменту запуска check_json_logs.py.

Скриншоты Server response для прогноза и /ready нужно сохранить без Curl и Authorization. Успех CI для изменений ЛР 7 проверяется после отправки ветки.
