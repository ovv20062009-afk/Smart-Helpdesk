# ЛР 5. Smart Helpdesk в Docker

Сервис получает обращение, определяет категорию и предлагает отдел. Если максимальная вероятность ниже 0.8 или в тексте нет знакомых слов, решение передаётся оператору.

ЛР 5 продолжает тему № 4. В методичке сказано, что пример с насосом приведён как образец. Здесь вместо телеметрии используются тексты обращений из ЛР 4.

## Что добавлено

| Файл | Назначение |
|---|---|
| Dockerfile | Две стадии сборки на python:3.11-slim, запуск без root |
| .dockerignore | В контекст входят только исходники сервиса, зависимости и артефакты |
| requirements.txt | Фиксированные версии библиотек сервиса |
| requirements-dev.txt | Дополнительные библиотеки подготовки и тестов |
| prepare_artifacts.py | Обучение классификатора на train из ЛР 4 и подготовка комплекта |
| src/api.py | FastAPI с /health и /predict |
| src/schemas.py | Проверка входа и схема ответа |
| src/artifacts.py | Загрузка и проверка артефактов при старте |
| src/preprocessing.py | Копия общего модуля ЛР 4 с проверкой совпадения |
| tests/test_api.py | Проверки API и обработки ошибок без Docker |
| tests/test_container.py | Четыре smoke-теста через настоящие HTTP-запросы |
| record_docker.py | Проверка контейнера, smoke-тесты и запись размера образа |
| docs/lab5_report.md | Отчёт и ответы на контрольные вопросы |
| ../.github/workflows/lab5.yml | Сборка и проверка контейнера в GitHub Actions |

Старые API и словарный классификатор из ЛР 2 и 3 остаются отдельной реализацией. В ЛР 5 используется обученная LogisticRegression. Её обучение добавлено здесь, потому что ЛР 4 создавала только признаки и препроцессор.

## 1. Подготовка артефактов

Нужны результаты ЛР 4: train.parquet, test.parquet и preprocessor.joblib. Если их нет, сначала запустите конвейер по lab4/README.md.

Из корня Smart-Helpdesk в PowerShell, по одной строке:

```powershell
cd lab5
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe prepare_artifacts.py
.\.venv\Scripts\python.exe -m pytest -q tests/test_api.py
```

На компьютере уже используется Python 3.12. В контейнере будет Python 3.11 по методичке. В GitHub Actions подготовка и работа контейнера проверяются на Python 3.11. Совместимость артефактов с контейнером подтверждают smoke-тесты. Версии scikit-learn, numpy, pandas и joblib должны совпадать; сервис проверяет их по manifest.json.

Скрипт не обучает TF-IDF заново. Он копирует препроцессор ЛР 4 и обучает LogisticRegression только на 48 строках train. 12 строк test используются для оценки. Формируются:

- artifacts/preprocessor.joblib;
- models/model.joblib;
- artifacts/manifest.json с версиями и контрольными суммами;
- docs/training_metrics.json.

Joblib-файлы не загружаются из сети и не включаются в Git. Они создаются локально из собственного учебного набора. Контрольные суммы помогают обнаружить повреждение и смешивание версий, но не заменяют доверие к источнику файла.

Обработчик очистки должен совпадать с ЛР 4. Скрипт проверяет это перед подготовкой. Различия переводов строк LF и CRLF при сравнении не учитываются.

## 2. Сборка и запуск

Установленный Docker Desktop должен быть запущен и работать в режиме Linux containers. Проверьте клиент и доступ к движку:

```powershell
docker --version
docker info
```

Из папки lab5:

```powershell
docker build --progress=plain -t smart-helpdesk:v1.0.0 .
docker image inspect smart-helpdesk:v1.0.0 --format '{{.Size}}'
docker run -d -p 127.0.0.1:8000:8000 --name smart-helpdesk-lab5 smart-helpdesk:v1.0.0
```

Точка в docker build обозначает папку lab5 как контекст. Не запускайте эту команду из корня Smart-Helpdesk: там находится Dockerfile прежней работы.

Порт 8000 должен быть свободен. Если в другом окне работает старый Uvicorn из ЛР 2, завершите его через Ctrl+C. Если контейнер с таким именем уже существует, сначала посмотрите `docker ps -a`; не создавайте второй с тем же именем.

## 3. Проверка через curl.exe

В PowerShell используйте именно curl.exe. JSON берётся из файла, поэтому кавычки и русские буквы не нужно экранировать в командной строке.

```powershell
curl.exe -i http://127.0.0.1:8000/health
curl.exe -i -X POST http://127.0.0.1:8000/predict -H "Content-Type: application/json" --data-binary "@request.json"
curl.exe -i -X POST http://127.0.0.1:8000/predict -H "Content-Type: application/json" --data-binary "@bad_request.json"
```

Ожидаются HTTP 200, HTTP 200 и HTTP 422. Вместо недопустимого давления из примера методички проверяется пустой текст обращения. Документация API доступна по http://127.0.0.1:8000/docs.

## 4. Автоматическая проверка контейнера

```powershell
.\.venv\Scripts\python.exe record_docker.py
```

Скрипт убеждается, что контейнер запущен из нужного образа и порт опубликован. Затем вызывает `pytest tests/test_container.py`. Проверки ждут готовности сервиса до 60 секунд. Сохраняются docs/container_tests.txt и docs/docker_result.json с ID и размером образа.

Отдельный вызов smoke-тестов:

```powershell
.\.venv\Scripts\python.exe -m pytest -q tests/test_container.py
```

Без запущенного сервиса smoke-тесты завершаются ошибкой. Обычная команда `pytest` по настройке pytest.ini выполняет только tests/test_api.py, без сетевых проверок.

В .dockerignore разрешены только serving-файлы и наши артефакты. Размер их содержимого оценивается в record_docker.py; фактический размер переданного контекста показывает Docker во время сборки. Порог контекста из методички составляет 200 МБ, а не размер самого образа.

Для просмотра состояния и логов:

```powershell
docker ps
docker logs smart-helpdesk-lab5
docker inspect smart-helpdesk-lab5 --format '{{.State.Health.Status}}'
```

HEALTHCHECK срабатывает периодически, поэтому сначала возможен статус starting. Если /health возвращает 503, посмотрите логи: артефакты могли отсутствовать, повредиться или оказаться несовместимыми.

Завершение и удаление только учебного контейнера:

```powershell
docker stop smart-helpdesk-lab5
docker rm smart-helpdesk-lab5
```

## Контракт API

Вход /predict:

| Поле | Ограничение |
|---|---|
| ticket_id | 1–100 символов: латинские буквы, цифры, дефис, подчёркивание |
| text | До 5000 символов, должен содержать слова |
| channel | web, email или chat; по умолчанию web |

Лишние поля запрещены. Пустой текст, неизвестный канал и лишние поля дают HTTP 422.

Ответ содержит ticket_id, category, confidence, destination, manual_review_required, model_version и preprocessor_version. При недостаточной уверенности категория остаётся предложением модели, а destination равен OPERATOR. При отсутствии знакомых слов category и confidence равны null.

Confidence берётся из predict_proba обученной модели. Калибровка не проверялась, поэтому это не гарантия правильности решения. Порог 0.8 взят из проекта ЛР 2 и на реальных данных потребует проверки.

GET /health возвращает 200 только после успешной загрузки и проверки комплекта. При проблеме возвращает 503, а /predict не выдаёт ложный прогноз. Во время ошибки самого вычисления /predict возвращает 500 с общим сообщением.

## Что проверено до Docker

При подготовке файлов прошли 16 тестов API. Ещё четыре smoke-теста прошли через локально запущенный HTTP-сервис без контейнера. Это проверка сетевых запросов, а не доказательство сборки Docker. Подробности находятся в docs/api_tests.txt, docs/http_tests.txt и docs/api_examples.json.

На маленьком учебном test получены accuracy 0.8333 и macro-F1 0.8320. Это 10 правильных ответов из 12, а не оценка качества на настоящих обращениях.

Контейнер проверен на Windows через Docker Desktop 22 ноября 2026 года. Образ smart-helpdesk:v1.0.0 собран, размер по docker image inspect составляет 149.64 МиБ. Контекст сборки по выводу Docker составляет 36.71 kB. Статус контейнера healthy, все 4 smoke-теста прошли. Запросы curl.exe дали HTTP 200, 200 и 422. Фактические результаты находятся в docs/docker_result.json, docs/container_tests.txt и docs/curl_results.json.

## Публикация

После локальной проверки, из корня Smart-Helpdesk:

```powershell
git switch -c feature/lab5-docker
git add lab5 .github/workflows/lab5.yml
git status
git commit -m "Добавить Docker-сервис Smart Helpdesk для ЛР 5"
git push -u origin feature/lab5-docker
```

Затем создайте Pull Request в main и дождитесь проверки Lab 5 Docker. Workflow заново создаёт результаты ЛР 4, обучает классификатор, собирает образ и запускает smoke-тесты в контейнере. Результаты доступны в артефакте lab5-docker-results.

Репозиторий: https://github.com/ovv20062009-afk/Smart-Helpdesk

Документация: https://fastapi.tiangolo.com/advanced/events/ и https://docs.docker.com/build/building/best-practices/
