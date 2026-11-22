"""HTTP-клиент без Streamlit, повторов запросов и вывода внутренних ошибок."""
from urllib.parse import urlsplit
from uuid import UUID

import requests

from frontend.request_validation import TicketInput
from frontend.response_validation import ApiResponse

TIMEOUT = (3, 10)
MESSAGES = {
    401: "Сервис не принял учетные данные. Проверьте настройку доступа.",
    403: "Для этого клиента запрещён разбор обращений.",
    422: "Сервер отклонил данные обращения. Проверьте заполнение формы.",
    429: "Лимит обращений исчерпан. Попробуйте позже.",
    503: "Сервис сейчас не может подготовить результат.",
}


class ApiClientError(Exception):
    def __init__(self, code, message, retry_after=None, trace_id=None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.retry_after = retry_after
        self.trace_id = trace_id


def safe_trace(value):
    try:
        trace = UUID(value)
        return str(trace) if trace.version == 4 else None
    except (ValueError, TypeError, AttributeError):
        return None


def request_prediction(api_url, token, payload):
    if not token:
        raise ApiClientError("config", "Не настроен доступ к сервису.")
    try:
        address = urlsplit(api_url)
        if (address.scheme not in ("http", "https") or not address.hostname
                or address.username or address.password or address.query or address.fragment):
            raise ValueError
    except (TypeError, ValueError):
        raise ApiClientError("config", "Некорректно настроен адрес сервиса.") from None
    try:
        checked = TicketInput.model_validate(payload)
    except (ValueError, TypeError):
        raise ApiClientError("input", "Проверьте идентификатор, текст и канал обращения.") from None
    try:
        response = requests.post(api_url.rstrip("/") + "/api/v1/predict",
            json=checked.model_dump(), headers={"Authorization": "Bearer " + token},
            timeout=TIMEOUT, allow_redirects=False)
    except requests.Timeout:
        raise ApiClientError("timeout", "Сервис не ответил за отведённое время.") from None
    except requests.ConnectionError:
        raise ApiClientError("connection", "Не удалось подключиться к сервису.") from None
    except requests.RequestException:
        raise ApiClientError("network", "Ошибка сетевого обмена.") from None
    trace = safe_trace(response.headers.get("X-Trace-ID"))
    if response.status_code != 200:
        message = MESSAGES.get(response.status_code, "Ошибка сервера." if response.status_code >= 500 else "Неожиданный ответ сервиса.")
        retry = response.headers.get("Retry-After") if response.status_code == 429 else None
        if retry is not None:
            retry = "".join(char for char in str(retry)[:128] if char.isprintable())
        raise ApiClientError(str(response.status_code), message, retry_after=retry, trace_id=trace)
    try:
        result = ApiResponse.model_validate(response.json())
    except (ValueError, TypeError):
        raise ApiClientError("contract", "Ответ сервиса не соответствует формату. Оценка не получена.", trace_id=trace) from None
    if result.ticket_id != checked.ticket_id:
        raise ApiClientError("contract", "Ответ относится к другому обращению. Оценка не получена.", trace_id=trace)
    header = response.headers.get("X-Trace-ID")
    if header is not None and header != str(result.trace_id):
        raise ApiClientError("contract", "Идентификаторы ответа не совпадают. Оценка не получена.")
    return result
