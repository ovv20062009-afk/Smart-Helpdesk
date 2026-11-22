# Smart Helpdesk v1.4.0

[![ML System CI/CD](https://github.com/ovv20062009-afk/Smart-Helpdesk/actions/workflows/ml-ci-cd.yml/badge.svg)](https://github.com/ovv20062009-afk/Smart-Helpdesk/actions/workflows/ml-ci-cd.yml)

ЛР 6 продолжает Docker-сервис из ЛР 5. Добавлены сквозной trace_id, JSON-логи, резервное правило при отказе модели и автоматическая доставка образа через GitHub Actions. Исторический отчёт ЛР 5 описывает проверенную ранее версию v1.0.0.

[Отчёт ЛР 6](../docs/lab6_report.md) и [Model Card](../MODEL_CARD.md).

## Подготовка

Из папки lab5 в CMD или PowerShell:

```text
.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.venv\Scripts\python.exe prepare_artifacts.py
.venv\Scripts\python.exe -m pytest -q
```

Если окружение ещё не создано: `py -3.12 -m venv .venv`. Нужны результаты ЛР 4: train.parquet, test.parquet и preprocessor.joblib. Команды их восстановления приведены в ../lab4/README.md.

После обновления кода prepare_artifacts.py выполняется обязательно. Он обновляет manifest.json под v1.4.0, проверяет совпадение подготовки текста с ЛР 4 и обучает небольшой классификатор на готовых признаках train. TF-IDF не переобучается. В CI подготовка идёт на Python 3.11, как и работа контейнера.

## Запуск Docker

Выполняйте из lab5. Если старый контейнер smart-helpdesk-lab5 из ЛР 5 ещё занимает порт 8000, остановите только его:

```text
docker stop smart-helpdesk-lab5
```

Сборка и запуск новой версии:

```text
docker build --progress=plain -t smart-helpdesk:v1.4.0 .
docker run -d -p 127.0.0.1:8000:8000 --name smart-helpdesk-lab6 smart-helpdesk:v1.4.0
.venv\Scripts\python.exe record_docker.py
```

record_docker.py проверяет ID образа, порт, smoke-тесты и размер образа. Результаты сохраняются в docs/lab6/container_tests.txt и docs/lab6/docker_result.json. Не запускайте новый контейнер, если контейнер с таким именем уже существует: сначала проверьте `docker ps -a`.

## Проверка API и Swagger

```text
curl.exe -i http://127.0.0.1:8000/health
curl.exe -i -X POST http://127.0.0.1:8000/predict -H "Content-Type: application/json" --data-binary "@request.json"
curl.exe -i -X POST http://127.0.0.1:8000/predict -H "Content-Type: application/json" --data-binary "@bad_request.json"
```

Ожидаются HTTP 200, 200 и 422. Откройте http://127.0.0.1:8000/docs, затем POST /predict и Try it out. Поля имеют описания. В ответе есть trace_id, model_version, source, latency_ms и решение по обращению.

X-Trace-ID в заголовке совпадает с trace_id в теле /predict и записи request_complete. Даже неверный запрос получает собственный идентификатор. Входящий X-Trace-ID не переиспользуется: сервис создаёт новый UUID4 для каждого запроса.

## Демонстрация Fallback

Второй контейнер использует тот же образ, но модель намеренно отключена:

```text
docker run -d -p 127.0.0.1:8001:8000 -e HELPDESK_DISABLE_MODEL=1 --name smart-helpdesk-lab6-fallback smart-helpdesk:v1.4.0
curl.exe -i -X POST http://127.0.0.1:8001/predict -H "Content-Type: application/json" --data-binary "@fallback_request.json"
```

Ожидаемый результат: HTTP 200, source=fallback_rule, TECHNICAL, IT_SUPPORT, confidence=null. Два разных ключевых слова «войти» и «пароль» проходят порог резервного правила. Повторы одного слова не считаются отдельными совпадениями. При одном слове, ничьей или отсутствии совпадений решение оставляется оператору.

HTTP 200 в резервном режиме не означает готовность модели. /health возвращает status=degraded, model_loaded=false и fallback_available=true. Ошибочный вход по-прежнему даёт 422, а не резервный прогноз.

## JSON-логи

Сервис и Uvicorn пишут JSON Lines в stdout. В CMD сохраните журнал и проверьте его:

```text
docker logs smart-helpdesk-lab6 > docs\lab6\container_logs.jsonl 2>&1
.venv\Scripts\python.exe check_json_logs.py docs\lab6\container_logs.jsonl
```

Затем можно добавить вторым аргументом check_json_logs.py скопированный trace_id из ответа: скрипт подтвердит его наличие. Для поиска вручную используйте `findstr /c:"UUID_ИЗ_ОТВЕТА" docs\lab6\container_logs.jsonl`, заменив UUID_ИЗ_ОТВЕТА фактическим значением.

В старом Windows PowerShell перенаправление `>` может сохранить файл в UTF-16. Для сохранения UTF-8 используйте:

```powershell
docker logs smart-helpdesk-lab6 2>&1 | Set-Content -Encoding utf8 docs\lab6\container_logs.jsonl
```

В логах есть trace_id, источник решения, HTTP-код и задержка. Текст обращения, Authorization, тело запроса и traceback не записываются. Примеры проверенных HTTP-логов без Docker находятся в docs/lab6/http_model_logs.jsonl и http_fallback_rule_logs.jsonl.

## Что проверяют тесты

Обычная команда pytest запускает юнит-тесты, TestClient, отказ модели и логирование. Сетевые smoke-тесты выполняются отдельно:

```text
.venv\Scripts\python.exe -m pytest -q tests/test_container.py
```

Тесты подтверждают совпадение trace_id, отсутствие секретов в логах, HTTP 422 для неверного входа, переход на Fallback при model=None, исключении или некорректных вероятностях, а также возврат к модели после временного сбоя.

## CI/CD

Файл ../.github/workflows/ml-ci-cd.yml запускается при push в main и ветки feature, а также при Pull Request в main. Его этапы:

1. Установка зависимостей с фиксированными версиями.
2. Линтинг и тесты прежних компонентов.
3. Проверка контрактов и конвейера ЛР 4.
4. Подготовка модели и тесты API, JSONL и Fallback.
5. Сборка образа с тегом SHA коммита.
6. Запуск обычного и резервного контейнеров, smoke-тесты и проверка логов.
7. Сохранение проверенного образа и Model Card в артефакт GitHub Actions.

Образ доступен в Actions, в успешном запуске, в разделе Artifacts под именем smart-helpdesk-image-SHA. Результаты проверки находятся в lab6-verification-SHA. Образ хранится 7 дней, результаты 14 дней. При необходимости доставки позже запустите workflow повторно через ручной wrapper lab5.yml.

Для загрузки скачанного tar.gz выполните `docker load -i ИМЯ_ФАЙЛА.tar.gz`, затем запустите образ с тегом SHA. Передача в registry или на внешний рабочий сервер в этой работе не настраивается.

Бейдж Passing можно подтвердить только после публикации и успешного выполнения нового workflow. Наличие YAML-файла само по себе не означает успешного CI.

## Результаты запуска на Windows

Образ smart-helpdesk:v1.4.0 собран и запущен в Docker Desktop. Размер образа составил 149.64 MiB. Основные тесты: 41 passed. Проверки обычного контейнера: 5 passed. Проверки контейнера с отключённой моделью: 5 passed. Docker healthcheck обычного контейнера: healthy. Страница Swagger открыта в браузере.

Сохранённый журнал резервного контейнера прошёл проверку: 13 JSON-строк и 7 записей запросов. Идентификатор из ответа найден в журнале. Подробности записаны в [результатах Windows](docs/lab6/windows_checks.md) и [отчёте ЛР 6](../docs/lab6_report.md). Эти результаты относятся к локальному запуску. Статус GitHub Actions проверяется отдельно после публикации.

## Паспорт модели и ограничения

MODEL_CARD.md содержит пять разделов, версию v1.4.0, источник данных, назначение, Precision и Recall по классам. Test содержит только 12 искусственных обращений. Качество на настоящих данных, калибровка вероятностей и точность резервного правила отдельно не измерялись.

Joblib-файлы создаются из собственного учебного набора. В Git сохраняются код и метаданные, а не бинарные артефакты. Внутри образа модель и препроцессор загружаются один раз на процесс.

## Публикация

Перед изменениями ЛР 6 создайте отдельную ветку после сохранения ЛР 5. Из корня Smart-Helpdesk:

```text
git switch -c feature/lab6-ci-cd
git add README.md MODEL_CARD.md docs/lab6_report.md lab5 .github/workflows/ml-ci-cd.yml .github/workflows/lab5.yml
git status
git commit -m "Добавить CI/CD, JSON-логи и Fallback для ЛР 6"
git push -u origin feature/lab6-ci-cd
```

Репозиторий: https://github.com/ovv20062009-afk/Smart-Helpdesk
