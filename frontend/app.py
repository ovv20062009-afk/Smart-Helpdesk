"""Форма Smart Helpdesk. Все вычисления модели выполняет отдельный API."""
from datetime import datetime, timezone
import os
from time import perf_counter

import pandas as pd
import streamlit as st

from frontend.api_client import ApiClientError, request_prediction
from frontend.history import append_history, export_csv, make_row
from frontend.request_validation import TicketInput

CATEGORIES = {"TECHNICAL": "Технический вопрос", "PAYMENT": "Оплата", "STUDY": "Учёба", None: "Не определена"}
DEPARTMENTS = {"IT_SUPPORT": "Техническая поддержка", "FINANCE": "Финансовый отдел", "STUDENT_OFFICE": "Учебный отдел", "OPERATOR": "Оператор"}
CHANNELS = {"web": "Сайт", "email": "Электронная почта", "chat": "Чат"}

st.set_page_config(page_title="Smart Helpdesk", page_icon="📨", layout="centered")
st.title("Разбор обращения")
st.caption("Учебная служба поддержки. Сервис предлагает тему и отдел для обращения.")
st.session_state.setdefault("history", [])
st.session_state.setdefault("current", None)

with st.form("ticket_form"):
    left, right = st.columns([2, 1])
    ticket_id = left.text_input("Номер обращения", value="T-8", max_chars=100,
        help="От 1 до 100 символов: латинские буквы, цифры, дефис и подчёркивание.")
    channel = right.selectbox("Канал", ["web", "email", "chat"], format_func=CHANNELS.get)
    text = st.text_area("Текст обращения", value="Не могу войти, забыла пароль", max_chars=5000,
        height=140, help="До 5000 символов. Для проверки используйте учебный текст без личных данных.")
    submitted = st.form_submit_button("Разобрать обращение", type="primary")

if submitted:
    st.session_state["current"] = None
    payload = {"ticket_id": ticket_id.strip(), "text": text, "channel": channel}
    requested_at = datetime.now(timezone.utc).isoformat()
    started = perf_counter()
    result = error = None
    try:
        try:
            TicketInput.model_validate(payload)
        except (ValueError, TypeError):
            raise ApiClientError("input", "Проверьте номер обращения и текст: номер содержит только латиницу, цифры, дефис и подчёркивание, а текст должен быть непустым.") from None
        with st.spinner("Разбираем обращение…"):
            result = request_prediction(os.getenv("API_URL", "http://127.0.0.1:8000"), os.getenv("API_TOKEN", ""), payload)
    except ApiClientError as exc:
        error = exc
        st.session_state["current"] = {"error": exc.message, "code": exc.code,
            "retry_after": exc.retry_after, "trace_id": exc.trace_id, "ticket_id": payload["ticket_id"]}
    else:
        st.session_state["current"] = {"result": result.model_dump(mode="json")}
    elapsed = (perf_counter() - started) * 1000
    row = make_row(payload, requested_at, elapsed, result=result, error=error)
    st.session_state["history"] = append_history(st.session_state["history"], row)

current = st.session_state["current"]
if current:
    st.subheader("Результат обращения")
    if "error" in current:
        st.error(current["error"])
        st.warning("По этому запросу оценка не получена.")
        if current.get("retry_after"):
            st.text("Рекомендация сервера Retry-After: " + current["retry_after"])
        st.text("Номер обращения: " + current["ticket_id"])
        if current.get("trace_id"):
            st.text("ID запроса: " + current["trace_id"])
    else:
        from frontend.response_validation import ApiResponse
        result = ApiResponse.model_validate(current["result"])
        p, m = result.prediction, result.metadata
        if m.degraded:
            st.warning("Резервный режим: модель недоступна, результат получен по ключевым словам.")
        elif p.manual_review_required:
            st.info("Нужна проверка оператора.")
        else:
            st.success("Сервис предложил отдел для обращения.")
        st.write("Номер обращения:", result.ticket_id)
        st.write("Тема:", CATEGORIES[p.category])
        st.write("Маршрут:", DEPARTMENTS[p.destination])
        st.write("Проверка оператора:", "нужна" if p.manual_review_required else "не требуется по учебному правилу")
        if p.confidence is None:
            st.write("Численная оценка не предоставлена.")
        else:
            st.metric("Оценка модели", f"{p.confidence:.3f}")
            st.caption("Это оценка модели, а не гарантия правильного решения.")
        st.text("Источник: " + m.source + "   Версия модели: " + m.model_version)
        st.text("ID запроса: " + str(result.trace_id))
        with st.expander("Время и правило маршрутизации"):
            st.write("Время ответа UTC:", m.timestamp_utc.isoformat())
            st.write("Длительность расчёта на сервере, мс:", m.latency_ms)
            st.write("Порог модели:", p.threshold_used)
            if m.degraded:
                st.write("Резервное правило использует два разных слова одной категории.")
                st.write("Совпадения:", ", ".join(p.matched_words) or "нет однозначного совпадения")

st.subheader("История сеанса")
st.caption("Последние 100 попыток. История временная, её можно сохранить в CSV.")
if st.button("Очистить историю"):
    st.session_state["history"] = []
    st.session_state["current"] = None
    st.rerun()
rows = st.session_state["history"]
if rows:
    frame = pd.DataFrame(rows)
    display = frame[["requested_at", "ticket_id", "status", "confidence", "destination", "source", "error_code"]].rename(columns={
        "requested_at": "Время UTC", "ticket_id": "Номер", "status": "Статус", "confidence": "Оценка",
        "destination": "Маршрут", "source": "Источник", "error_code": "Ошибка"})
    display["Статус"] = display["Статус"].map({"success": "Отдел предложен", "manual": "Проверка оператора", "degraded": "Резервный режим", "error": "Ошибка"})
    display["Маршрут"] = display["Маршрут"].map(DEPARTMENTS)
    display["Источник"] = display["Источник"].map({"model": "Модель", "fallback_rule": "Резервное правило"})
    st.dataframe(display, hide_index=True)
    st.download_button("Скачать CSV", data=export_csv(rows), file_name="helpdesk_history.csv", mime="text/csv")
else:
    st.write("Пока обращений нет.")
