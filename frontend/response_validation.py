"""Клиентская копия контракта маршрутизации из ЛР 7."""
from datetime import datetime, timedelta
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, StrictBool, UUID4, model_validator

Category = Literal["TECHNICAL", "PAYMENT", "STUDY"]
Destination = Literal["IT_SUPPORT", "FINANCE", "STUDENT_OFFICE", "OPERATOR"]
DEPARTMENTS = {"TECHNICAL": "IT_SUPPORT", "PAYMENT": "FINANCE", "STUDY": "STUDENT_OFFICE"}


class ContractModel(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class Prediction(ContractModel):
    category: Category | None
    confidence: float | None = Field(ge=0, le=1, strict=True)
    destination: Destination
    manual_review_required: StrictBool
    threshold_used: float = Field(gt=0, le=1, strict=True)
    matched_words: list[str] = Field(default_factory=list)


class Metadata(ContractModel):
    model_version: str = Field(min_length=1)
    preprocessor_version: str = Field(min_length=1)
    timestamp_utc: datetime
    latency_ms: float = Field(ge=0, strict=True)
    source: Literal["model", "fallback_rule"]
    degraded: StrictBool


class ApiResponse(ContractModel):
    trace_id: UUID4
    ticket_id: str = Field(min_length=1, max_length=100, pattern=r"^[A-Za-z0-9_-]+$")
    prediction: Prediction
    metadata: Metadata

    @model_validator(mode="after")
    def check_consistency(self):
        p, m = self.prediction, self.metadata
        if m.timestamp_utc.utcoffset() != timedelta(0):
            raise ValueError("Серверное время должно содержать UTC")
        if m.source == "fallback_rule":
            if not m.degraded or p.confidence is not None:
                raise ValueError("Несогласованный резервный режим")
            words = p.matched_words
            if len(set(words)) != len(words) or any(not word.strip() for word in words):
                raise ValueError("Некорректные совпадения правила")
            if p.category is None:
                if words or not p.manual_review_required or p.destination != "OPERATOR":
                    raise ValueError("Неоднозначный результат требует оператора")
            else:
                if not words or p.manual_review_required != (len(words) < 2):
                    raise ValueError("Решение не соответствует порогу правила")
        else:
            if m.degraded or p.matched_words:
                raise ValueError("Несогласованный результат модели")
            if p.category is None:
                if p.confidence is not None or not p.manual_review_required or p.destination != "OPERATOR":
                    raise ValueError("Неизвестный текст требует ручной проверки")
            elif p.confidence is None or p.manual_review_required != (p.confidence < p.threshold_used):
                raise ValueError("Решение не соответствует порогу модели")
        if p.category is not None:
            expected = "OPERATOR" if p.manual_review_required else DEPARTMENTS[p.category]
            if p.destination != expected:
                raise ValueError("Категория и отдел не согласованы")
        return self
